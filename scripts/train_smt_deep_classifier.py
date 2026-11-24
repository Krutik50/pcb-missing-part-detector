"""
Offline Deep Learning SMT Component Classifier Training Pipeline
Trains an end-to-end multi-class convolutional neural network on the 500-board
physical dataset across all 7 SMT component states:
  0: OK_COMPONENT
  1: MISSING
  2: TILTED
  3: MISALIGNED
  4: BRIDGED
  5: POLARITY_REVERSED
  6: TOMBSTONED

100% Offline, runs locally on standard CPU in < 1 minute.
Saves trained weights to app/core/physical_metric_weights.pt and benchmark to results/deep_classifier_benchmark.json.
"""

import json
import time
from pathlib import Path
import cv2
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import torchvision.transforms as T

ROOT = Path(__file__).resolve().parent.parent

CLASS_NAMES = [
    "OK_COMPONENT",
    "MISSING",
    "TILTED",
    "MISALIGNED",
    "BRIDGED",
    "POLARITY_REVERSED",
    "TOMBSTONED",
]
CLASS_MAP = {name.lower(): idx for idx, name in enumerate(CLASS_NAMES)}
CLASS_MAP["ok"] = 0
CLASS_MAP["present"] = 0


class SMTDeepDefectClassifier(nn.Module):
    """Fast, accurate 3-stage convolutional network for SMT defect classification."""
    def __init__(self, num_classes=7):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),  # 32x32

            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),  # 16x16

            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((1, 1))  # 1x1
        )
        self.classifier = nn.Sequential(
            nn.Linear(128, 64),
            nn.ReLU(inplace=True),
            nn.Dropout(0.2),
            nn.Linear(64, num_classes)
        )

    def forward(self, x):
        feat = self.features(x)
        feat = torch.flatten(feat, 1)
        return self.classifier(feat)


class SMTPhysicalCropDataset(Dataset):
    def __init__(self, crops, labels, transform=None):
        self.crops = crops
        self.labels = labels
        self.transform = transform

    def __len__(self):
        return len(self.crops)

    def __getitem__(self, idx):
        img_bgr = self.crops[idx]
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        label = self.labels[idx]

        if self.transform:
            tensor = self.transform(img_rgb)
        else:
            tensor = torch.from_numpy(img_rgb.transpose(2, 0, 1)).float() / 255.0

        return tensor, label


def extract_crops_from_manifest(manifest_path, split="train"):
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    boards = data.get("boards", {})
    images = data.get("images", {})

    crops = []
    labels = []

    data_dir = manifest_path.parent

    for rel_path, img_info in images.items():
        if img_info.get("split") != split:
            continue

        full_img_path = data_dir / rel_path
        if not full_img_path.exists():
            continue

        img = cv2.imread(str(full_img_path))
        if img is None:
            continue

        b_type = img_info.get("board_type")
        board_meta = boards.get(b_type, {})
        components = board_meta.get("components", {})
        defects = img_info.get("defects", {})

        for cname, cinfo in components.items():
            bx, by, bw, bh = cinfo["bbox"]
            ih, iw = img.shape[:2]
            # Bounding box bounds check
            bx0 = max(0, min(bx, iw - 1))
            by0 = max(0, min(by, ih - 1))
            bw0 = max(4, min(bw, iw - bx0))
            bh0 = max(4, min(bh, ih - by0))

            crop = img[by0:by0+bh0, bx0:bx0+bw0]
            if crop.size == 0:
                continue

            # Resize to uniform 64x64
            crop_64 = cv2.resize(crop, (64, 64), interpolation=cv2.INTER_AREA)

            # Determine class label
            if cname in defects:
                dtype = defects[cname]["type"].lower()
                cid = CLASS_MAP.get(dtype, 1)
            else:
                cid = 0  # OK_COMPONENT

            crops.append(crop_64)
            labels.append(cid)

    return crops, labels


def train_smt_defect_classifier(epochs=5, batch_size=32, lr=0.001):
    gt_file = ROOT / "data" / "multiboard" / "ground_truth_multiboard.json"
    if not gt_file.exists():
        print(f"Error: manifest not found at {gt_file}")
        return

    print("=" * 80)
    print("TRAINING OFFLINE SMT DEEP DEFECT CLASSIFIER (PyTorch CPU)")
    print("=" * 80)

    t_start = time.perf_counter()

    print("Extracting training and validation crops from 500 physical boards...")
    train_crops, train_labels = extract_crops_from_manifest(gt_file, split="train")
    val_crops, val_labels = extract_crops_from_manifest(gt_file, split="test")

    print(f"Total Training Crops   : {len(train_crops)}")
    print(f"Total Validation Crops : {len(val_crops)}")

    # Class distribution
    unique, counts = np.unique(train_labels, return_counts=True)
    dist = {CLASS_NAMES[u]: int(c) for u, c in zip(unique, counts)}
    print(f"Training Class Distribution: {dist}")

    transform_train = T.Compose([
        T.ToPILImage(),
        T.RandomHorizontalFlip(p=0.3),
        T.ColorJitter(brightness=0.15, contrast=0.15),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])

    transform_val = T.Compose([
        T.ToPILImage(),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])

    train_ds = SMTPhysicalCropDataset(train_crops, train_labels, transform=transform_train)
    val_ds = SMTPhysicalCropDataset(val_crops, val_labels, transform=transform_val)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    device = torch.device("cpu")
    model = SMTDeepDefectClassifier(num_classes=len(CLASS_NAMES)).to(device)

    # Compute class weights for imbalanced classes
    total_samples = len(train_labels)
    class_weights = np.ones(len(CLASS_NAMES), dtype=np.float32)
    for u, c in zip(unique, counts):
        class_weights[u] = total_samples / (len(CLASS_NAMES) * float(c))
    weights_tensor = torch.tensor(class_weights, dtype=torch.float32).to(device)

    criterion = nn.CrossEntropyLoss(weight=weights_tensor)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)

    best_val_acc = 0.0

    print(f"\nTraining for {epochs} epochs on CPU...")
    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0

        for inputs, targets in train_loader:
            inputs, targets = inputs.to(device), targets.to(device)
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()

            running_loss += loss.item() * inputs.size(0)
            _, preds = outputs.max(1)
            correct += preds.eq(targets).sum().item()
            total += targets.size(0)

        epoch_loss = running_loss / total
        epoch_acc = (correct / total) * 100.0

        # Evaluate on validation set
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0

        with torch.no_grad():
            for inputs, targets in val_loader:
                inputs, targets = inputs.to(device), targets.to(device)
                outputs = model(inputs)
                loss = criterion(outputs, targets)
                val_loss += loss.item() * inputs.size(0)
                _, preds = outputs.max(1)
                val_correct += preds.eq(targets).sum().item()
                val_total += targets.size(0)

        val_loss = val_loss / val_total
        val_acc = (val_correct / val_total) * 100.0

        print(f"Epoch {epoch}/{epochs} | Train Loss: {epoch_loss:.4f} Acc: {epoch_acc:.1f}% | Val Loss: {val_loss:.4f} Acc: {val_acc:.1f}%")
        if val_acc > best_val_acc:
            best_val_acc = val_acc

    # Full Evaluation & Confusion Matrix on Held-Out Validation Split
    model.eval()
    all_preds = []
    all_targets = []
    with torch.no_grad():
        for inputs, targets in val_loader:
            inputs = inputs.to(device)
            outputs = model(inputs)
            _, preds = outputs.max(1)
            all_preds.extend(preds.cpu().numpy())
            all_targets.extend(targets.numpy())

    all_preds = np.array(all_preds)
    all_targets = np.array(all_targets)

    val_accuracy = float(np.mean(all_preds == all_targets) * 100.0)

    # Per-class metrics
    class_metrics = {}
    for c_idx, c_name in enumerate(CLASS_NAMES):
        tp = int(np.sum((all_preds == c_idx) & (all_targets == c_idx)))
        fp = int(np.sum((all_preds == c_idx) & (all_targets != c_idx)))
        fn = int(np.sum((all_preds != c_idx) & (all_targets == c_idx)))
        prec = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        rec = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        class_metrics[c_name] = {
            "samples": int(np.sum(all_targets == c_idx)),
            "precision": round(prec, 3),
            "recall": round(rec, 3),
            "f1_score": round(f1, 3),
        }

    elapsed_s = round(time.perf_counter() - t_start, 2)

    # Save weights
    weights_path = ROOT / "app" / "core" / "physical_metric_weights.pt"
    torch.save(model.state_dict(), str(weights_path))
    print(f"\nTrained model weights saved to: {weights_path}")

    # Save benchmark
    benchmark_file = ROOT / "results" / "deep_classifier_benchmark.json"
    benchmark_file.parent.mkdir(parents=True, exist_ok=True)
    bench_data = {
        "model_architecture": "SMTDeepDefectClassifier (3-stage ConvNet + BatchNorm + AdaptiveAvgPool)",
        "num_classes": len(CLASS_NAMES),
        "classes": CLASS_NAMES,
        "dataset": "500 Physical PCB Boards (350 Train / 150 Held-Out Validation)",
        "epochs": epochs,
        "training_time_seconds": elapsed_s,
        "device": str(device),
        "validation_accuracy": round(val_accuracy, 2),
        "per_class_metrics": class_metrics,
    }
    with open(benchmark_file, "w", encoding="utf-8") as f:
        json.dump(bench_data, f, indent=2)

    print(f"Benchmark report saved to: {benchmark_file}")
    print("\n" + "=" * 80)
    print(f"OFFLINE DEEP LEARNING MODEL TRAINING COMPLETE (Time: {elapsed_s}s)")
    print(f"Validation Accuracy: {val_accuracy:.2f}% across {len(val_labels)} component crops")
    print("=" * 80)
    for c_name, m in class_metrics.items():
        print(f"  {c_name:<18}: Precision={m['precision']:.3f}, Recall={m['recall']:.3f}, F1={m['f1_score']:.3f} (N={m['samples']})")
    print("=" * 80)


if __name__ == "__main__":
    train_smt_defect_classifier(epochs=5, batch_size=32, lr=0.001)
