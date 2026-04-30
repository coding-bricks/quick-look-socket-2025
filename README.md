# Ichnos

Ichnos is a Python-based application for real-time monitoring and visualization of FITS data, combining a Flask web interface with interactive Bokeh dashboards.

---

## Features

* Real-time monitoring of FITS files
* Interactive visualization with Bokeh
* Web interface powered by Flask and Socket.IO
* Support for network-mounted file systems (via polling observer)

---

## Requirements

* Python **3.10 or 3.11**
* `pip` and `venv`

---

## Installation

Clone the repository:

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```

Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Upgrade pip (recommended):

```bash
pip install --upgrade pip
```

Install the project in editable mode:

```bash
pip install -e .
```

---

## Running the Application

You can start the application with:

```bash
python -m ichnos
```

or, if installed correctly:

```bash
ichnos
```

---

## Project Structure

```
repo/
+-- ichnos/            # Main application package
|   +-- __main__.py    # Entry point for `python -m ichnos`
|   +-- app.py         # Main application logic
|   +-- ...
+-- static/            # Static assets (JS, CSS, etc.)
+-- templates/         # HTML templates
+-- pyproject.toml     # Project configuration
+-- README.md
```

---

## Notes on Dependencies

This project intentionally pins some dependencies to specific version ranges to ensure compatibility:

* Bokeh `< 3.0` (breaking API changes in newer versions)
* Flask `< 3.0`
* NumPy `< 2.0`
* Watchdog `== 2.1.0` (required for PollingObserver behavior)

Installing newer versions may break the application.

---

## ?? Development Notes

The project is installed in **editable mode** (`pip install -e .`), which means:

* Source code changes are immediately reflected
* No need to reinstall after every modification

---

## Troubleshooting

### Bokeh errors (e.g. `Panel(child=...)`)

You are likely using Bokeh = 3.0.
Solution: ensure correct version constraints are installed.

### Watchdog issues (PollingObserver not working)

Ensure:

```
watchdog==2.1.0
```

---

## Future Improvements

* Migration to newer Bokeh versions
* Automated testing (CI)
* Dependency locking for full reproducibility

---

## License

MIT License

---

## Author

Fabio Schirru (fabio.schirru@inaf.it)

---
