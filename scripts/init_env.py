"""Gera as credenciais locais do Docker Compose."""
import os
from pathlib import Path
from secrets import token_hex


values = {
    "SAFEVISION_ADMIN_PASSWORD": token_hex(12),
    "SAFEVISION_SESSION_SECRET": token_hex(32),
    "POSTGRES_PASSWORD": token_hex(16),
    "SAFEVISION_S3_SECRET_KEY": token_hex(16),
}


def main():
    lines = Path(".env.example").read_text().splitlines()
    content = "\n".join(f"{line}{values.get(line[:-1], '')}" if line.endswith("=") else line for line in lines)
    try:
        descriptor = os.open(".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print("Use o arquivo .env existente.")
        return
    with os.fdopen(descriptor, "w") as file:
        file.write(content + "\n")
    print("Credenciais locais gravadas em .env.")


if __name__ == "__main__":
    main()
