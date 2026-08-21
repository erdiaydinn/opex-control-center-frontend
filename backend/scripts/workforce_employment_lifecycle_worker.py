"""Apply due Employee Master exits and queue IdP revocation atomically."""

from app.modules.workforce.service import initialize_workforce, process_due_employment_exits


if __name__ == "__main__":
    initialize_workforce()
    print(process_due_employment_exits())
