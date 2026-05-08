*&---------------------------------------------------------------------*
*& Conceptual template: Z_SAPMCP_HEALTH_CHECK
*&---------------------------------------------------------------------*
*& Purpose:
*&   Read-only technical health check for sapmcp PRD/QAS pilots.
*&
*& Status:
*&   TEMPLATE ONLY. Not production-ready. Adapt DDIC types, logging,
*&   authorization object and checks to the customer system.
*&---------------------------------------------------------------------*

FUNCTION z_sapmcp_health_check.
*"----------------------------------------------------------------------
*" RFC-enabled function module (conceptual interface)
*" IMPORTING
*"   VALUE(iv_profile) TYPE char20 DEFAULT 'QUICK'
*" EXPORTING
*"   VALUE(ev_ok)      TYPE abap_bool
*"   VALUE(ev_sid)     TYPE sy-sysid
*"   VALUE(ev_mandt)   TYPE sy-mandt
*"   VALUE(ev_summary) TYPE string
*" TABLES
*"   et_checks STRUCTURE zsapmcp_health_check
*"----------------------------------------------------------------------

  DATA lv_profile TYPE char20.
  lv_profile = to_upper( iv_profile ).
  IF lv_profile IS INITIAL.
    lv_profile = 'QUICK'.
  ENDIF.

  "Use a customer authorization object, not SAP_ALL/SAP_NEW.
  AUTHORITY-CHECK OBJECT 'Z_SAPMCP'
    ID 'ACTVT' FIELD '03'
    ID 'ZAREA' FIELD 'HEALTH'.
  IF sy-subrc <> 0.
    RAISE EXCEPTION TYPE zcx_sapmcp_no_authority.
  ENDIF.

  ev_sid = sy-sysid.
  ev_mandt = sy-mandt.
  ev_ok = abap_true.

  "Recommended production behavior:
  "- return counts and statuses, not raw dumps/syslog lines;
  "- keep a short runtime budget;
  "- log who called the RFC and which profile was used;
  "- avoid SELECT * and avoid business tables.

  CLEAR et_checks[].

  APPEND VALUE #(
    check_name = 'SYSTEM'
    status     = 'OK'
    metric     = sy-sysid
    message    = 'RFC reached ABAP system'
  ) TO et_checks.

  "Examples to implement carefully:
  "- count cancelled jobs in last N hours (display only);
  "- count update errors;
  "- count current enqueue locks;
  "- count dumps without returning dump payload;
  "- return UNKNOWN if the check is not authorized.

  ev_summary = |{ sy-sysid }/{ sy-mandt } health profile { lv_profile } executed|.

  "TODO: write Application Log (SLG1) object ZSAPMCP subobject HEALTH.

ENDFUNCTION.
