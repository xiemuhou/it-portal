/*
Run using an existing SQL Server database administrator account.
Scope: itPortal only. No server-wide or other database grants.
This script grants deployment privileges; it does not create application tables
or delete, replace, or import existing business data.
*/
USE [itPortal];
GO
IF SUSER_ID(N'itportal_app') IS NULL
    THROW 51000, 'SQL Server login itportal_app does not exist.', 1;
GO
IF DATABASE_PRINCIPAL_ID(N'itportal_app') IS NULL
    CREATE USER [itportal_app] FOR LOGIN [itportal_app];
GO
GRANT CONNECT TO [itportal_app];
GRANT VIEW DEFINITION TO [itportal_app];
GRANT CREATE TABLE TO [itportal_app];
GRANT ALTER, REFERENCES, SELECT, INSERT, UPDATE, DELETE ON SCHEMA::[dbo] TO [itportal_app];
GO
/* After migrations are complete, the administrator may revoke deployment-only
   CREATE TABLE, ALTER, REFERENCES, and VIEW DEFINITION permissions according to
   the deployment process. Keep the runtime SELECT/INSERT/UPDATE/DELETE grants.
   SQL Server backup is managed independently by the DBA and does not require
   granting backup privileges to the portal application login. */
