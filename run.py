"""Entry point for PyInstaller-packaged OpenSandbox Dashboard."""
import os, sys

if __name__ == "__main__":
    # ponytail: PyInstaller onefile bundles to sys._MEIPASS
    if getattr(sys, "frozen", False):
        bundle = sys._MEIPASS
    else:
        bundle = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(bundle, "app.py")
    sys.argv = ["streamlit", "run", app_path, "--server.headless", "true",
                "--server.port", "8501", "--server.address", "0.0.0.0",
                "--browser.gatherUsageStats", "false",
                "--global.developmentMode", "false"]
    from streamlit.web import cli as st_cli
    st_cli.main()
