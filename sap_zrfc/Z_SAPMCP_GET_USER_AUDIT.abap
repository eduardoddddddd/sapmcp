*&---------------------------------------------------------------------*
*& Conceptual template: Z_SAPMCP_GET_USER_AUDIT
*&---------------------------------------------------------------------*
*& Purpose:
*&   Controlled read-only user audit for sapmcp without exposing broad
*&   SU01/SUIM data by default.
*&
*& Status:
*&   TEMPLATE ONLY. Not production-ready. Adapt to customer policy,
*&   user groups and privacy requirements.
*&---------------------------------------------------------------------*

FUNCTION z_sapmcp_get_user_audit.
*"----------------------------------------------------------------------
*" RFC-enabled function module (conceptual interface)
*" IMPORTING
*"   VALUE(iv_bname)          TYPE xubname
*"   VALUE(iv_include_roles)  TYPE abap_bool DEFAULT abap_false
*" EXPORTING
*"   VALUE(es_user)           TYPE zsapmcp_user_audit
*" TABLES
*"   et_roles    STRUCTURE zsapmcp_user_role
*"   et_profiles STRUCTURE zsapmcp_user_profile
*"----------------------------------------------------------------------

  DATA lv_bname TYPE xubname.
  lv_bname = to_upper( iv_bname ).

  IF lv_bname IS INITIAL.
    RAISE EXCEPTION TYPE zcx_sapmcp_invalid_input.
  ENDIF.

  AUTHORITY-CHECK OBJECT 'Z_SAPMCP'
    ID 'ACTVT' FIELD '03'
    ID 'ZAREA' FIELD 'USER_AUDIT'.
  IF sy-subrc <> 0.
    RAISE EXCEPTION TYPE zcx_sapmcp_no_authority.
  ENDIF.

  "Optional: restrict by user group to avoid broad PRD exposure.
  "AUTHORITY-CHECK OBJECT 'S_USER_GRP'
  "  ID 'ACTVT' FIELD '03'
  "  ID 'CLASS' FIELD <resolved_user_group>.

  CLEAR: es_user, et_roles[], et_profiles[].

  SELECT SINGLE bname, gltgv, gltgb, trdat, ltime, uflag, locnt, class
    FROM usr02
    WHERE bname = @lv_bname
    INTO @DATA(ls_usr02).
  IF sy-subrc <> 0.
    RAISE EXCEPTION TYPE zcx_sapmcp_not_found.
  ENDIF.

  es_user-bname        = ls_usr02-bname.
  es_user-valid_from   = ls_usr02-gltgv.
  es_user-valid_to     = ls_usr02-gltgb.
  es_user-last_logon_d = ls_usr02-trdat.
  es_user-last_logon_t = ls_usr02-ltime.
  es_user-lock_status  = ls_usr02-uflag.
  es_user-failed_count = ls_usr02-locnt.
  es_user-user_group   = ls_usr02-class.

  IF iv_include_roles = abap_true.
    "Return only role names and validity, not derived sensitive metadata.
    SELECT agr_name, from_dat, to_dat
      FROM agr_users
      WHERE uname = @lv_bname
      INTO TABLE @DATA(lt_roles).

    LOOP AT lt_roles ASSIGNING FIELD-SYMBOL(<role>).
      APPEND VALUE #(
        agr_name = <role>-agr_name
        from_dat = <role>-from_dat
        to_dat   = <role>-to_dat
      ) TO et_roles.
    ENDLOOP.
  ENDIF.

  "Profiles are high-risk in PRD. Prefer returning only a boolean SAP_ALL
  "indicator or require a second approval flag.
  SELECT profile
    FROM ust04
    WHERE bname = @lv_bname
    INTO TABLE @DATA(lt_profiles).

  LOOP AT lt_profiles ASSIGNING FIELD-SYMBOL(<profile>).
    APPEND VALUE #( profile = <profile>-profile ) TO et_profiles.
    IF <profile>-profile = 'SAP_ALL'.
      es_user-has_sap_all = abap_true.
    ENDIF.
  ENDLOOP.

  "TODO: write Application Log (SLG1) object ZSAPMCP subobject USER_AUDIT
  "with caller, target user, include_roles flag and returned volume.

ENDFUNCTION.
