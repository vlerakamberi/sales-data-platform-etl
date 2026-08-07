# Setup guide

## Supported environment

- Supported Python family: `>=3.13,<3.14`
- Validated interpreter: CPython 3.13.14

## Canonical setup

1. Confirm Python 3.13.x:

   ```text
   python --version
   ```

2. Create the local virtual environment:

   ```text
   python -m venv .venv
   ```

3. Activate it. In Windows PowerShell or the VS Code PowerShell terminal:

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

   In Windows Command Prompt:

   ```bat
   .venv\Scripts\activate.bat
   ```

   On POSIX-compatible shells:

   ```sh
   source .venv/bin/activate
   ```

4. Optionally, and recommended, upgrade pip:

   ```text
   python -m pip install --upgrade pip
   ```

   A pip upgrade is not mandatory for the project setup.

5. Install the project and required development tools in editable mode:

   ```text
   python -m pip install -e ".[dev]"
   ```

6. Create a local `.env` from the safe template. PowerShell example:

   ```powershell
   Copy-Item .env.example .env
   ```

   The real `.env` is ignored and must not be committed.

7. Run the application and validation commands:

   ```text
   python -m sales_data_platform
   python -m pytest
   python -m ruff check .
   python -m ruff format --check .
   python -m pip check
   ```

Application semantics are platform-neutral. Shell-specific differences are
limited to virtual-environment activation and file-copy commands.

See the [configuration guide](configuration-guide.md) before changing local
settings and the [development guide](development-guide.md) before contributing.
