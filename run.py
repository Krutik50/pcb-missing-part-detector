import uvicorn

if __name__ == "__main__":
    print("=" * 65)
    print("  PCB Missing Component Detector - Task B (Offline System)")
    print("  Starting server at: http://127.0.0.1:8000")
    print("  Press Ctrl+C to stop.")
    print("=" * 65)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
