# SAP RFC Python Connector (No pyrfc)

A lightweight and production-ready Python connector for calling SAP RFC
functions directly using the official **SAP NetWeaver RFC SDK (C library)**.

This project was created as a **drop-in alternative to `pyrfc`**, focusing on
simplicity, transparency, and long-term maintainability.

---

## Who is this for?

- SAP developers and integration engineers
- Python developers working with SAP ECC or S/4HANA
- Teams migrating away from `pyrfc`
- Backend services, ETL jobs, and integrations

This is **not a framework** — it is a clean and reusable bridge that you can
adapt to your own architecture.

---

## Key Features

- Direct RFC calls using SAP NetWeaver RFC SDK (C library)
- No dependency on `pyrfc`
- Single-file connector (easy to audit and modify)
- Supports:
  - Import parameters
  - Export parameters
  - Simple tables
  - Related (logical nested) tables
- Compatible with Python 3.9+
- Designed for enterprise and backend use cases

---

## Requirements

- SAP NetWeaver RFC SDK installed
- Access to a SAP ECC or S/4HANA system
- RFC-enabled function modules
- SAP BASIS or system administrator access for setup

> ⚠️ The SAP NetWeaver RFC SDK installation and RFC authorizations must be
> performed by a SAP BASIS or system administrator.

---

## SAP Environment Setup (BASIS Required)

The following steps must be executed by a SAP administrator:

1. Install **SAP NetWeaver RFC SDK** on the target machine
2. Ensure the `sapnwrfc.dll` (Windows) or shared library is accessible
3. Create or assign an RFC user
4. Grant authorization to execute the desired RFC function modules
5. Ensure custom Z functions are marked as **Remote-Enabled**

---

## Environment Configuration

Copy the `.env.example` file and adjust the values:

```env
SAP_ASHOST=your_sap_host
SAP_SYSNR=00
SAP_CLIENT=100
SAP_USER=RFC_USER
SAP_PASS=********
SAP_LANG=EN
