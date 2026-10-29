/* Run manually as an EHR database administrator after replacing the login.
   The portal application never executes this file.  No table/view data is changed. */
USE [EHR_DATABASE];
GO

/* Create the database user only when the login has not yet been mapped here.
   Replace itportal_ehr_reader with the dedicated SQL Server login name. */
IF DATABASE_PRINCIPAL_ID(N'itportal_ehr_reader') IS NULL
    CREATE USER [itportal_ehr_reader] FOR LOGIN [itportal_ehr_reader];
GO

GRANT SELECT ON OBJECT::dbo.V_Employee TO [itportal_ehr_reader];
GRANT SELECT ON OBJECT::dbo.V_Department TO [itportal_ehr_reader];
GRANT SELECT ON OBJECT::dbo.V_Employee_JOB TO [itportal_ehr_reader];
GO

/* Verification: this should return exactly the three explicitly granted objects. */
SELECT OBJECT_SCHEMA_NAME(major_id) AS schema_name,
       OBJECT_NAME(major_id) AS object_name,
       permission_name
FROM sys.database_permissions
WHERE grantee_principal_id = DATABASE_PRINCIPAL_ID(N'itportal_ehr_reader')
  AND permission_name = N'SELECT';
GO
