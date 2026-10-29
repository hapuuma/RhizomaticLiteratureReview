import sys
import os
import multiprocessing
import uvicorn
from pathlib import Path

def setup_paths():
    """Sets up the environment paths correctly for both dev and bundled EXE."""
    if hasattr(sys, '_MEIPASS'):
        # Running as a PyInstaller bundle
        # sys._MEIPASS is a temporary folder where PyInstaller unpacks data
        base_path = Path(sys._MEIPASS)
        # The .exe itself usually lives in the folder where the user ran it
        # We want user-writable data (like .env and data/) to be near the .exe
        exe_dir = Path(sys.executable).parent.absolute()
        os.environ["RHIZOMATIC_EXE_DIR"] = str(exe_dir)
    else:
        # Running in development
        base_path = Path(__file__).parent.absolute()
        os.environ["RHIZOMATIC_EXE_DIR"] = str(base_path)

    # Add root to path for 'from backend.main import app'
    if str(base_path) not in sys.path:
        sys.path.insert(0, str(base_path))

    # Add 'backend' to path for internal imports
    backend_path = base_path / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))
    
    return base_path

if __name__ == "__main__":
    # Crucial for PyInstaller + multiprocessing on Windows
    multiprocessing.freeze_support()
    
    # Setup paths before importing app
    BASE_PATH = setup_paths()
    
    print(f"[*] Starting Rhizomatic Research Agent...")
    print(f"[*] Base Path (Resources): {BASE_PATH}")
    print(f"[*] Executable Directory (Data/Config): {os.environ['RHIZOMATIC_EXE_DIR']}")

    # Import inside main to prevent double-import side effects during worker spawns
    try:
        from backend.main import app
        # Use 0.0.0.0 to be consistent and more accessible
        # On Windows, uvicorn.run(app) is better than uvicorn.run("backend.main:app") 
        # when frozen because it avoids complex module re-importing.
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info", reload=False)
    except Exception as e:
        print(f"[!] Critical Error during startup: {e}")
        import traceback
        traceback.print_exc()
        # Keep window open on error if running as EXE
        if hasattr(sys, '_MEIPASS'):
            input("Press Enter to exit...")
        sys.exit(1)
