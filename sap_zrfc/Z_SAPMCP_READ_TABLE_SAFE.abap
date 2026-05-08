*&---------------------------------------------------------------------*
*& Conceptual template: Z_SAPMCP_READ_TABLE_SAFE
*&---------------------------------------------------------------------*
*& Purpose:
*&   Safer alternative to unrestricted RFC_READ_TABLE for sapmcp.
*&
*& Status:
*&   TEMPLATE ONLY. Not production-ready. Implement with customer DDIC
*&   types and strict allowlists. Do not transport as-is.
*&---------------------------------------------------------------------*

FUNCTION z_sapmcp_read_table_safe.
*"----------------------------------------------------------------------
*" RFC-enabled function module (conceptual interface)
*" IMPORTING
*"   VALUE(iv_table)     TYPE tabname
*"   VALUE(iv_max_rows)  TYPE i DEFAULT 100
*" TABLES
*"   it_fields STRUCTURE zsapmcp_field_request
*"   it_filter STRUCTURE zsapmcp_filter_request
*"   et_rows   STRUCTURE zsapmcp_row_value
*"----------------------------------------------------------------------

  DATA lv_table    TYPE tabname.
  DATA lv_max_rows TYPE i.

  lv_table = to_upper( iv_table ).
  lv_max_rows = iv_max_rows.
  IF lv_max_rows IS INITIAL OR lv_max_rows > 200.
    lv_max_rows = 200.
  ENDIF.

  AUTHORITY-CHECK OBJECT 'Z_SAPMCP'
    ID 'ACTVT' FIELD '03'
    ID 'ZAREA' FIELD 'TABLE'
    ID 'ZTAB'  FIELD lv_table.
  IF sy-subrc <> 0.
    RAISE EXCEPTION TYPE zcx_sapmcp_no_authority.
  ENDIF.

  "Mandatory allowlist. Example customizing table:
  "  ZSAPMCP_TAB_ALLOW with TABNAME, ENVIRONMENT, MAX_ROWS, ENABLED.
  "Do not accept arbitrary table names in PRD.
  SELECT SINGLE tabname
    FROM zsapmcp_tab_allow
    WHERE tabname = @lv_table
      AND enabled = @abap_true
    INTO @DATA(lv_allowed_table).
  IF sy-subrc <> 0.
    RAISE EXCEPTION TYPE zcx_sapmcp_not_allowed.
  ENDIF.

  "Validate requested fields against DD03L and a customer allowlist.
  "Reject empty field lists, LRAW/RAWSTRING/BLOB-like data, cluster/pool
  "tables if not explicitly approved, and sensitive fields by policy.

  LOOP AT it_fields ASSIGNING FIELD-SYMBOL(<field>).
    DATA(lv_field) = to_upper( <field>-fieldname ).

    SELECT SINGLE fieldname
      FROM dd03l
      WHERE tabname = @lv_table
        AND fieldname = @lv_field
        AND as4local = 'A'
      INTO @DATA(lv_ddic_field).
    IF sy-subrc <> 0.
      RAISE EXCEPTION TYPE zcx_sapmcp_invalid_field.
    ENDIF.

    SELECT SINGLE fieldname
      FROM zsapmcp_field_allow
      WHERE tabname = @lv_table
        AND fieldname = @lv_field
        AND enabled = @abap_true
      INTO @DATA(lv_allowed_field).
    IF sy-subrc <> 0.
      RAISE EXCEPTION TYPE zcx_sapmcp_not_allowed.
    ENDIF.
  ENDLOOP.

  "Filters should be structured, not free SQL strings.
  "Recommended filter model:
  "  FIELDNAME, OPERATOR(EQ/BT/GE/LE), LOW, HIGH
  "Validate each field/operator/value before building Open SQL.
  "For production, prefer explicit CASE branches per allowed table rather
  "than generic dynamic SQL.

  "Pseudo-code only:
  "CASE lv_table.
  "  WHEN 'T000'.
  "    SELECT mandt, mtext
  "      FROM t000
  "      WHERE mandt IN @lt_mandt_range
  "      UP TO @lv_max_rows ROWS
  "      INTO TABLE @lt_t000.
  "    map lt_t000 to et_rows.
  "  WHEN 'TBTCO'.
  "    SELECT jobname, jobcount, status, sdlstrtdt, sdlstrttm
  "      FROM tbtco
  "      WHERE sdlstrtdt >= @lv_from_date
  "      UP TO @lv_max_rows ROWS
  "      INTO TABLE @lt_tbtco.
  "    map lt_tbtco to et_rows.
  "  WHEN OTHERS.
  "    RAISE EXCEPTION TYPE zcx_sapmcp_not_allowed.
  "ENDCASE.

  "TODO: write Application Log (SLG1) object ZSAPMCP subobject READ_TABLE
  "with table, field count, filter count, row count and caller.

ENDFUNCTION.
