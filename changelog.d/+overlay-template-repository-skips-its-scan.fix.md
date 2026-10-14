The `scan` workflow in the overlay template now skips the template repository itself, which is
public and owned by an organisation and so failed every run for want of a gitleaks licence key. An
overlay generated from the template is not itself a template and still runs the scan.
