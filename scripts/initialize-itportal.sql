/* Generated schema reference for a NEW EMPTY itPortal database only.
   This deployment has already been initialized. Do not run over an existing database.
   Prefer `python -m alembic upgrade head` for versioned deployments. */
USE [itPortal];
GO
BEGIN TRANSACTION;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

GO

-- Running upgrade  -> 0001_business

CREATE TABLE sites (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    code VARCHAR(64) NOT NULL, 
    name NVARCHAR(128) NOT NULL, 
    site_type VARCHAR(32) NOT NULL, 
    address NVARCHAR(512) NULL, 
    is_enabled BIT NOT NULL, 
    CONSTRAINT pk_sites PRIMARY KEY (id), 
    CONSTRAINT uq_sites_0 UNIQUE (code)
);

GO

CREATE INDEX ix_sites_0 ON sites (site_type, is_enabled);

GO

CREATE TABLE departments (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    code VARCHAR(64) NOT NULL, 
    name NVARCHAR(128) NOT NULL, 
    parent_id VARCHAR(36) NULL, 
    is_enabled BIT NOT NULL, 
    CONSTRAINT pk_departments PRIMARY KEY (id), 
    CONSTRAINT uq_departments_0 UNIQUE (code), 
    CONSTRAINT fk_departments_parent_id FOREIGN KEY(parent_id) REFERENCES departments (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_departments_0 ON departments (parent_id);

GO

CREATE TABLE roles (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    code VARCHAR(64) NOT NULL, 
    name NVARCHAR(128) NOT NULL, 
    description NVARCHAR(512) NULL, 
    is_builtin BIT NOT NULL, 
    CONSTRAINT pk_roles PRIMARY KEY (id), 
    CONSTRAINT uq_roles_0 UNIQUE (code)
);

GO

CREATE TABLE permissions (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    code VARCHAR(128) NOT NULL, 
    name NVARCHAR(128) NOT NULL, 
    module_code VARCHAR(64) NOT NULL, 
    supports_data_scope BIT NOT NULL, 
    CONSTRAINT pk_permissions PRIMARY KEY (id), 
    CONSTRAINT uq_permissions_0 UNIQUE (code)
);

GO

CREATE INDEX ix_permissions_0 ON permissions (module_code);

GO

CREATE TABLE dictionary_items (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    dictionary_code VARCHAR(64) NOT NULL, 
    item_code VARCHAR(64) NOT NULL, 
    label NVARCHAR(128) NOT NULL, 
    sort_order INTEGER NOT NULL, 
    is_enabled BIT NOT NULL, 
    CONSTRAINT pk_dictionary_items PRIMARY KEY (id), 
    CONSTRAINT uq_dictionary_items_0 UNIQUE (dictionary_code, item_code)
);

GO

CREATE INDEX ix_dictionary_items_0 ON dictionary_items (dictionary_code, is_enabled);

GO

CREATE TABLE vendors (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    code VARCHAR(64) NOT NULL, 
    name NVARCHAR(200) NOT NULL, 
    contact_name NVARCHAR(128) NULL, 
    contact_phone NVARCHAR(64) NULL, 
    contact_email NVARCHAR(254) NULL, 
    support_phone NVARCHAR(64) NULL, 
    CONSTRAINT pk_vendors PRIMARY KEY (id), 
    CONSTRAINT uq_vendors_0 UNIQUE (code)
);

GO

CREATE TABLE ticket_categories (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    code VARCHAR(64) NOT NULL, 
    name NVARCHAR(128) NOT NULL, 
    parent_id VARCHAR(36) NULL, 
    description NVARCHAR(512) NULL, 
    is_enabled BIT NOT NULL, 
    sort_order INTEGER NOT NULL, 
    CONSTRAINT pk_ticket_categories PRIMARY KEY (id), 
    CONSTRAINT uq_ticket_categories_0 UNIQUE (code), 
    CONSTRAINT fk_ticket_categories_parent_id FOREIGN KEY(parent_id) REFERENCES ticket_categories (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_ticket_categories_0 ON ticket_categories (parent_id, is_enabled);

GO

CREATE TABLE knowledge_categories (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    code VARCHAR(64) NOT NULL, 
    name NVARCHAR(128) NOT NULL, 
    parent_id VARCHAR(36) NULL, 
    sort_order INTEGER NOT NULL, 
    is_enabled BIT NOT NULL, 
    CONSTRAINT pk_knowledge_categories PRIMARY KEY (id), 
    CONSTRAINT uq_knowledge_categories_0 UNIQUE (code), 
    CONSTRAINT fk_knowledge_categories_parent_id FOREIGN KEY(parent_id) REFERENCES knowledge_categories (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_knowledge_categories_0 ON knowledge_categories (parent_id);

GO

CREATE TABLE external_links (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    link_code VARCHAR(64) NOT NULL, 
    name NVARCHAR(128) NOT NULL, 
    url NVARCHAR(2048) NOT NULL, 
    open_mode VARCHAR(16) NOT NULL, 
    is_public BIT NOT NULL, 
    is_enabled BIT NOT NULL, 
    sort_order INTEGER NOT NULL, 
    CONSTRAINT pk_external_links PRIMARY KEY (id), 
    CONSTRAINT uq_external_links_0 UNIQUE (link_code)
);

GO

CREATE INDEX ix_external_links_0 ON external_links (is_public, is_enabled);

GO

CREATE TABLE background_jobs (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    job_type VARCHAR(64) NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    payload_json NTEXT NOT NULL, 
    job_state VARCHAR(32) NOT NULL, 
    run_after DATETIME2(3) NOT NULL, 
    lease_until DATETIME2(3) NULL, 
    worker_key VARCHAR(128) NULL, 
    attempt_count INTEGER NOT NULL, 
    max_attempts INTEGER NOT NULL, 
    progress_percent INTEGER NOT NULL, 
    error_code VARCHAR(64) NULL, 
    started_at DATETIME2(3) NULL, 
    finished_at DATETIME2(3) NULL, 
    CONSTRAINT pk_background_jobs PRIMARY KEY (id), 
    CONSTRAINT uq_background_jobs_0 UNIQUE (idempotency_key)
);

GO

CREATE INDEX ix_background_jobs_1 ON background_jobs (lease_until);

GO

CREATE INDEX ix_background_jobs_0 ON background_jobs (job_state, run_after);

GO

CREATE TABLE data_sources (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    source_code VARCHAR(64) NOT NULL, 
    name NVARCHAR(128) NOT NULL, 
    source_type VARCHAR(32) NOT NULL, 
    safe_config_json NTEXT NOT NULL, 
    is_enabled BIT NOT NULL, 
    CONSTRAINT pk_data_sources PRIMARY KEY (id), 
    CONSTRAINT uq_data_sources_0 UNIQUE (source_code)
);

GO

CREATE TABLE system_settings (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    setting_key VARCHAR(128) NOT NULL, 
    value_json NTEXT NOT NULL, 
    description NVARCHAR(512) NULL, 
    CONSTRAINT pk_system_settings PRIMARY KEY (id), 
    CONSTRAINT uq_system_settings_0 UNIQUE (setting_key)
);

GO

CREATE TABLE knowledge_recommendation_configs (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    profile_code VARCHAR(64) NOT NULL, 
    mode VARCHAR(32) NOT NULL, 
    endpoint_url NVARCHAR(2048) NULL, 
    api_contract_version VARCHAR(32) NOT NULL, 
    model_name NVARCHAR(128) NULL, 
    credential_ref VARCHAR(128) NULL, 
    timeout_ms INTEGER NOT NULL, 
    max_results INTEGER NOT NULL, 
    description_send_policy VARCHAR(32) NOT NULL, 
    allowed_hosts_json NTEXT NULL, 
    is_enabled BIT NOT NULL, 
    CONSTRAINT pk_knowledge_recommendation_configs PRIMARY KEY (id), 
    CONSTRAINT uq_knowledge_recommendation_configs_0 UNIQUE (profile_code)
);

GO

CREATE TABLE import_templates (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    template_code VARCHAR(64) NOT NULL, 
    template_version VARCHAR(32) NOT NULL, 
    module_code VARCHAR(64) NOT NULL, 
    name NVARCHAR(128) NOT NULL, 
    file_format VARCHAR(16) NOT NULL, 
    field_spec_json NTEXT NOT NULL, 
    safe_example_json NTEXT NULL, 
    schema_sha256 VARCHAR(64) NOT NULL, 
    is_enabled BIT NOT NULL, 
    CONSTRAINT pk_import_templates PRIMARY KEY (id), 
    CONSTRAINT uq_import_templates_0 UNIQUE (template_code, template_version)
);

GO

CREATE INDEX ix_import_templates_0 ON import_templates (module_code, is_enabled);

GO

CREATE TABLE locations (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    site_id VARCHAR(36) NOT NULL, 
    parent_id VARCHAR(36) NULL, 
    code VARCHAR(64) NOT NULL, 
    name NVARCHAR(128) NOT NULL, 
    location_type VARCHAR(32) NOT NULL, 
    sort_order INTEGER NOT NULL, 
    CONSTRAINT pk_locations PRIMARY KEY (id), 
    CONSTRAINT uq_locations_0 UNIQUE (site_id, code), 
    CONSTRAINT fk_locations_site_id FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_locations_parent_id FOREIGN KEY(parent_id) REFERENCES locations (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_locations_0 ON locations (site_id, parent_id);

GO

CREATE TABLE users (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    login_name VARCHAR(128) NOT NULL, 
    display_name NVARCHAR(128) NOT NULL, 
    employee_no VARCHAR(64) NULL, 
    department_id VARCHAR(36) NOT NULL, 
    site_id VARCHAR(36) NULL, 
    email NVARCHAR(254) NULL, 
    phone NVARCHAR(64) NULL, 
    password_hash VARCHAR(512) NOT NULL, 
    account_state VARCHAR(32) NOT NULL, 
    auth_version INTEGER NOT NULL, 
    last_login_at DATETIME2(3) NULL, 
    CONSTRAINT pk_users PRIMARY KEY (id), 
    CONSTRAINT uq_users_0 UNIQUE (login_name), 
    CONSTRAINT fk_users_department_id FOREIGN KEY(department_id) REFERENCES departments (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_users_site_id FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_users_0 ON users (department_id, account_state);

GO

CREATE TABLE role_permissions (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    role_id VARCHAR(36) NOT NULL, 
    permission_id VARCHAR(36) NOT NULL, 
    data_scope VARCHAR(32) NOT NULL, 
    CONSTRAINT pk_role_permissions PRIMARY KEY (id), 
    CONSTRAINT uq_role_permissions_0 UNIQUE (role_id, permission_id), 
    CONSTRAINT fk_role_permissions_role_id FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_role_permissions_permission_id FOREIGN KEY(permission_id) REFERENCES permissions (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_role_permissions_0 ON role_permissions (permission_id, role_id);

GO

CREATE TABLE network_scopes (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    site_id VARCHAR(36) NOT NULL, 
    scope_code VARCHAR(64) NOT NULL, 
    name NVARCHAR(128) NOT NULL, 
    description NVARCHAR(512) NULL, 
    CONSTRAINT pk_network_scopes PRIMARY KEY (id), 
    CONSTRAINT uq_network_scopes_0 UNIQUE (site_id, scope_code), 
    CONSTRAINT fk_network_scopes_site_id FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_network_scopes_0 ON network_scopes (site_id);

GO

CREATE TABLE service_catalog (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    service_code VARCHAR(64) NOT NULL, 
    name NVARCHAR(128) NOT NULL, 
    summary NVARCHAR(512) NOT NULL, 
    scope_text NTEXT NULL, 
    submission_guide NTEXT NULL, 
    category_id VARCHAR(36) NULL, 
    service_hours NVARCHAR(256) NULL, 
    contact_text NVARCHAR(512) NULL, 
    is_published BIT NOT NULL, 
    sort_order INTEGER NOT NULL, 
    CONSTRAINT pk_service_catalog PRIMARY KEY (id), 
    CONSTRAINT uq_service_catalog_0 UNIQUE (service_code), 
    CONSTRAINT fk_service_catalog_category_id FOREIGN KEY(category_id) REFERENCES ticket_categories (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_service_catalog_0 ON service_catalog (is_published, sort_order);

GO

CREATE TABLE site_aliases (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    site_id VARCHAR(36) NOT NULL, 
    alias_name NVARCHAR(128) NOT NULL, 
    alias_key VARCHAR(64) NOT NULL, 
    CONSTRAINT pk_site_aliases PRIMARY KEY (id), 
    CONSTRAINT uq_site_aliases_0 UNIQUE (alias_key), 
    CONSTRAINT fk_site_aliases_site_id FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_site_aliases_0 ON site_aliases (site_id);

GO

CREATE TABLE user_roles (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    user_id VARCHAR(36) NOT NULL, 
    role_id VARCHAR(36) NOT NULL, 
    CONSTRAINT pk_user_roles PRIMARY KEY (id), 
    CONSTRAINT uq_user_roles_0 UNIQUE (user_id, role_id), 
    CONSTRAINT fk_user_roles_user_id FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_user_roles_role_id FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_user_roles_0 ON user_roles (role_id, user_id);

GO

CREATE TABLE user_sessions (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    csrf_hash VARCHAR(64) NOT NULL, 
    auth_version INTEGER NOT NULL, 
    expires_at DATETIME2(3) NOT NULL, 
    idle_expires_at DATETIME2(3) NOT NULL, 
    last_seen_at DATETIME2(3) NOT NULL, 
    revoked_at DATETIME2(3) NULL, 
    CONSTRAINT pk_user_sessions PRIMARY KEY (id), 
    CONSTRAINT uq_user_sessions_0 UNIQUE (token_hash), 
    CONSTRAINT fk_user_sessions_user_id FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_user_sessions_1 ON user_sessions (expires_at);

GO

CREATE INDEX ix_user_sessions_0 ON user_sessions (user_id, expires_at);

GO

CREATE TABLE resources (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    resource_kind VARCHAR(32) NOT NULL, 
    resource_code VARCHAR(64) NOT NULL, 
    name NVARCHAR(200) NOT NULL, 
    site_id VARCHAR(36) NOT NULL, 
    location_id VARCHAR(36) NULL, 
    owner_user_id VARCHAR(36) NULL, 
    lifecycle_status VARCHAR(32) NOT NULL, 
    verification_status VARCHAR(32) NOT NULL, 
    verified_at DATETIME2(3) NULL, 
    verified_by_user_id VARCHAR(36) NULL, 
    CONSTRAINT pk_resources PRIMARY KEY (id), 
    CONSTRAINT uq_resources_0 UNIQUE (resource_code), 
    CONSTRAINT fk_resources_site_id FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_resources_location_id FOREIGN KEY(location_id) REFERENCES locations (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_resources_owner_user_id FOREIGN KEY(owner_user_id) REFERENCES users (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_resources_0 ON resources (resource_kind, site_id, is_archived);

GO

CREATE INDEX ix_resources_1 ON resources (owner_user_id, is_archived);

GO

CREATE INDEX ix_resources_2 ON resources (verification_status);

GO

CREATE TABLE contracts (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    contract_code VARCHAR(64) NOT NULL, 
    external_number NVARCHAR(128) NULL, 
    vendor_id VARCHAR(36) NOT NULL, 
    title NVARCHAR(200) NOT NULL, 
    contract_type VARCHAR(32) NOT NULL, 
    start_date DATETIME NULL, 
    end_date DATETIME NULL, 
    amount NUMERIC(18, 2) NULL, 
    currency_code VARCHAR(3) NOT NULL, 
    billing_cycle VARCHAR(32) NOT NULL, 
    source_term_text NVARCHAR(512) NULL, 
    contact_user_id VARCHAR(36) NULL, 
    CONSTRAINT pk_contracts PRIMARY KEY (id), 
    CONSTRAINT uq_contracts_0 UNIQUE (contract_code), 
    CONSTRAINT fk_contracts_vendor_id FOREIGN KEY(vendor_id) REFERENCES vendors (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_contracts_contact_user_id FOREIGN KEY(contact_user_id) REFERENCES users (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_contracts_0 ON contracts (end_date, is_archived);

GO

CREATE INDEX ix_contracts_1 ON contracts (vendor_id);

GO

CREATE TABLE tickets (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    ticket_number VARCHAR(64) NOT NULL, 
    origin VARCHAR(32) NOT NULL, 
    requester_user_id VARCHAR(36) NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    requester_name_snapshot NVARCHAR(128) NOT NULL, 
    department_name_snapshot NVARCHAR(128) NULL, 
    contact_snapshot NVARCHAR(512) NULL, 
    category_id VARCHAR(36) NULL, 
    site_id VARCHAR(36) NULL, 
    location_id VARCHAR(36) NULL, 
    location_text NVARCHAR(256) NULL, 
    title NVARCHAR(200) NOT NULL, 
    description NTEXT NOT NULL, 
    impact_scope VARCHAR(32) NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    assignee_user_id VARCHAR(36) NULL, 
    current_cycle_no INTEGER NOT NULL, 
    submitted_at DATETIME2(3) NOT NULL, 
    first_started_at DATETIME2(3) NULL, 
    completed_at DATETIME2(3) NULL, 
    closed_at DATETIME2(3) NULL, 
    next_followup_at DATETIME2(3) NULL, 
    cancelled_at DATETIME2(3) NULL, 
    terminal_reason NVARCHAR(1024) NULL, 
    CONSTRAINT pk_tickets PRIMARY KEY (id), 
    CONSTRAINT uq_tickets_0 UNIQUE (ticket_number), 
    CONSTRAINT fk_tickets_requester_user_id FOREIGN KEY(requester_user_id) REFERENCES users (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_tickets_category_id FOREIGN KEY(category_id) REFERENCES ticket_categories (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_tickets_site_id FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_tickets_location_id FOREIGN KEY(location_id) REFERENCES locations (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_tickets_assignee_user_id FOREIGN KEY(assignee_user_id) REFERENCES users (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_tickets_0 ON tickets (requester_user_id, submitted_at);

GO

CREATE INDEX ix_tickets_4 ON tickets (site_id, completed_at);

GO

CREATE INDEX ix_tickets_2 ON tickets (status, submitted_at);

GO

CREATE INDEX ix_tickets_3 ON tickets (category_id, completed_at);

GO

CREATE INDEX ix_tickets_1 ON tickets (assignee_user_id, status, updated_at);

GO

CREATE TABLE file_objects (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    storage_key VARCHAR(256) NOT NULL, 
    original_name NVARCHAR(256) NOT NULL, 
    mime_type VARCHAR(128) NOT NULL, 
    size_bytes BIGINT NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    purpose VARCHAR(32) NOT NULL, 
    uploaded_by_user_id VARCHAR(36) NULL, 
    file_state VARCHAR(32) NOT NULL, 
    expires_at DATETIME2(3) NULL, 
    encryption_profile_ref VARCHAR(128) NULL, 
    CONSTRAINT pk_file_objects PRIMARY KEY (id), 
    CONSTRAINT uq_file_objects_0 UNIQUE (storage_key), 
    CONSTRAINT fk_file_objects_uploaded_by_user_id FOREIGN KEY(uploaded_by_user_id) REFERENCES users (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_file_objects_1 ON file_objects (expires_at);

GO

CREATE INDEX ix_file_objects_0 ON file_objects (purpose, file_state);

GO

CREATE TABLE knowledge_articles (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    article_code VARCHAR(64) NOT NULL, 
    category_id VARCHAR(36) NOT NULL, 
    title NVARCHAR(200) NOT NULL, 
    summary NVARCHAR(1024) NULL, 
    tags_text NVARCHAR(512) NULL, 
    publication_state VARCHAR(32) NOT NULL, 
    published_version_no INTEGER NULL, 
    published_at DATETIME2(3) NULL, 
    published_by_user_id VARCHAR(36) NULL, 
    CONSTRAINT pk_knowledge_articles PRIMARY KEY (id), 
    CONSTRAINT uq_knowledge_articles_0 UNIQUE (article_code), 
    CONSTRAINT fk_knowledge_articles_category_id FOREIGN KEY(category_id) REFERENCES knowledge_categories (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_knowledge_articles_published_by_user_id FOREIGN KEY(published_by_user_id) REFERENCES users (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_knowledge_articles_0 ON knowledge_articles (category_id, publication_state);

GO

CREATE TABLE improvement_projects (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    project_code VARCHAR(64) NOT NULL, 
    title NVARCHAR(200) NOT NULL, 
    problem_summary NVARCHAR(1024) NOT NULL, 
    implementation_text NTEXT NOT NULL, 
    outcome_text NTEXT NOT NULL, 
    start_date DATETIME NULL, 
    finish_date DATETIME NULL, 
    owner_user_id VARCHAR(36) NULL, 
    publication_state VARCHAR(32) NOT NULL, 
    published_at DATETIME2(3) NULL, 
    CONSTRAINT pk_improvement_projects PRIMARY KEY (id), 
    CONSTRAINT uq_improvement_projects_0 UNIQUE (project_code), 
    CONSTRAINT fk_improvement_projects_owner_user_id FOREIGN KEY(owner_user_id) REFERENCES users (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_improvement_projects_0 ON improvement_projects (publication_state, published_at);

GO

CREATE TABLE audit_logs (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    actor_user_id VARCHAR(36) NULL, 
    actor_name_snapshot NVARCHAR(128) NULL, 
    action_code VARCHAR(128) NOT NULL, 
    target_type VARCHAR(64) NOT NULL, 
    target_id VARCHAR(64) NULL, 
    request_id VARCHAR(64) NOT NULL, 
    occurred_at DATETIME2(3) NOT NULL, 
    result_code VARCHAR(32) NOT NULL, 
    changes_json NTEXT NULL, 
    reason NVARCHAR(1024) NULL, 
    CONSTRAINT pk_audit_logs PRIMARY KEY (id), 
    CONSTRAINT fk_audit_logs_actor_user_id FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_audit_logs_1 ON audit_logs (actor_user_id, occurred_at);

GO

CREATE INDEX ix_audit_logs_0 ON audit_logs (occurred_at);

GO

CREATE INDEX ix_audit_logs_2 ON audit_logs (target_type, target_id, occurred_at);

GO

CREATE TABLE idempotency_keys (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    actor_user_id VARCHAR(36) NOT NULL, 
    operation_code VARCHAR(64) NOT NULL, 
    key_hash VARCHAR(64) NOT NULL, 
    request_hash VARCHAR(64) NOT NULL, 
    result_object_id VARCHAR(64) NULL, 
    result_status INTEGER NULL, 
    expires_at DATETIME2(3) NOT NULL, 
    CONSTRAINT pk_idempotency_keys PRIMARY KEY (id), 
    CONSTRAINT uq_idempotency_keys_0 UNIQUE (actor_user_id, operation_code, key_hash), 
    CONSTRAINT fk_idempotency_keys_actor_user_id FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_idempotency_keys_0 ON idempotency_keys (expires_at);

GO

CREATE TABLE role_permission_sites (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    role_permission_id VARCHAR(36) NOT NULL, 
    site_id VARCHAR(36) NOT NULL, 
    CONSTRAINT pk_role_permission_sites PRIMARY KEY (id), 
    CONSTRAINT uq_role_permission_sites_0 UNIQUE (role_permission_id, site_id), 
    CONSTRAINT fk_role_permission_sites_role_permission_id FOREIGN KEY(role_permission_id) REFERENCES role_permissions (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_role_permission_sites_site_id FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_role_permission_sites_0 ON role_permission_sites (site_id);

GO

CREATE TABLE role_permission_departments (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    role_permission_id VARCHAR(36) NOT NULL, 
    department_id VARCHAR(36) NOT NULL, 
    CONSTRAINT pk_role_permission_departments PRIMARY KEY (id), 
    CONSTRAINT uq_role_permission_departments_0 UNIQUE (role_permission_id, department_id), 
    CONSTRAINT fk_role_permission_departments_role_permission_id FOREIGN KEY(role_permission_id) REFERENCES role_permissions (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_role_permission_departments_department_id FOREIGN KEY(department_id) REFERENCES departments (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_role_permission_departments_0 ON role_permission_departments (department_id);

GO

CREATE TABLE announcements (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    announcement_code VARCHAR(64) NOT NULL, 
    title NVARCHAR(200) NOT NULL, 
    summary NVARCHAR(512) NULL, 
    body NTEXT NOT NULL, 
    publication_state VARCHAR(32) NOT NULL, 
    is_pinned BIT NOT NULL, 
    sort_order INTEGER NOT NULL, 
    published_at DATETIME2(3) NULL, 
    published_by_user_id VARCHAR(36) NULL, 
    expires_at DATETIME2(3) NULL, 
    CONSTRAINT pk_announcements PRIMARY KEY (id), 
    CONSTRAINT uq_announcements_0 UNIQUE (announcement_code), 
    CONSTRAINT fk_announcements_published_by_user_id FOREIGN KEY(published_by_user_id) REFERENCES users (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_announcements_1 ON announcements (expires_at);

GO

CREATE INDEX ix_announcements_0 ON announcements (publication_state, is_pinned, published_at);

GO

CREATE TABLE devices (
    resource_id VARCHAR(36) NOT NULL, 
    device_type_code VARCHAR(64) NOT NULL, 
    manufacturer NVARCHAR(128) NULL, 
    model NVARCHAR(128) NULL, 
    hostname NVARCHAR(128) NULL, 
    warranty_start DATETIME NULL, 
    warranty_end DATETIME NULL, 
    CONSTRAINT pk_devices PRIMARY KEY (resource_id), 
    CONSTRAINT fk_devices_resource_id FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_devices_0 ON devices (warranty_end);

GO

CREATE TABLE circuits (
    resource_id VARCHAR(36) NOT NULL, 
    vendor_id VARCHAR(36) NOT NULL, 
    circuit_number NVARCHAR(128) NULL, 
    downstream_mbps NUMERIC(12, 3) NULL, 
    upstream_mbps NUMERIC(12, 3) NULL, 
    connection_mode_code VARCHAR(64) NULL, 
    role_code VARCHAR(32) NOT NULL, 
    purpose NVARCHAR(512) NULL, 
    CONSTRAINT pk_circuits PRIMARY KEY (resource_id), 
    CONSTRAINT fk_circuits_resource_id FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_circuits_vendor_id FOREIGN KEY(vendor_id) REFERENCES vendors (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_circuits_0 ON circuits (vendor_id);

GO

CREATE TABLE resource_contracts (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    resource_id VARCHAR(36) NOT NULL, 
    contract_id VARCHAR(36) NOT NULL, 
    relation_role VARCHAR(32) NOT NULL, 
    CONSTRAINT pk_resource_contracts PRIMARY KEY (id), 
    CONSTRAINT uq_resource_contracts_0 UNIQUE (resource_id, contract_id, relation_role), 
    CONSTRAINT fk_resource_contracts_resource_id FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_resource_contracts_contract_id FOREIGN KEY(contract_id) REFERENCES contracts (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_resource_contracts_0 ON resource_contracts (contract_id);

GO

CREATE TABLE vlans (
    resource_id VARCHAR(36) NOT NULL, 
    scope_id VARCHAR(36) NOT NULL, 
    vlan_number INTEGER NOT NULL, 
    purpose NVARCHAR(512) NULL, 
    CONSTRAINT pk_vlans PRIMARY KEY (resource_id), 
    CONSTRAINT uq_vlans_0 UNIQUE (scope_id, vlan_number), 
    CONSTRAINT fk_vlans_resource_id FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_vlans_scope_id FOREIGN KEY(scope_id) REFERENCES network_scopes (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_vlans_0 ON vlans (scope_id);

GO

CREATE TABLE wifi_networks (
    resource_id VARCHAR(36) NOT NULL, 
    ssid NVARCHAR(128) NOT NULL, 
    ssid_key VARCHAR(64) NOT NULL, 
    site_id VARCHAR(36) NOT NULL, 
    auth_method_code VARCHAR(64) NULL, 
    coverage NVARCHAR(512) NULL, 
    isolation_description NVARCHAR(512) NULL, 
    purpose NVARCHAR(512) NULL, 
    CONSTRAINT pk_wifi_networks PRIMARY KEY (resource_id), 
    CONSTRAINT uq_wifi_networks_0 UNIQUE (site_id, ssid_key), 
    CONSTRAINT fk_wifi_networks_resource_id FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_wifi_networks_site_id FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE NO ACTION
);

GO

CREATE TABLE ticket_cycles (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    ticket_id VARCHAR(36) NOT NULL, 
    cycle_no INTEGER NOT NULL, 
    opened_at DATETIME2(3) NOT NULL, 
    started_at DATETIME2(3) NULL, 
    completed_at DATETIME2(3) NULL, 
    closed_at DATETIME2(3) NULL, 
    ended_at DATETIME2(3) NULL, 
    end_kind VARCHAR(32) NULL, 
    duration_ms BIGINT NULL, 
    category_id VARCHAR(36) NULL, 
    final_handler_id VARCHAR(36) NULL, 
    final_handler_name_snapshot NVARCHAR(128) NULL, 
    handling_summary NTEXT NULL, 
    CONSTRAINT pk_ticket_cycles PRIMARY KEY (id), 
    CONSTRAINT uq_ticket_cycles_0 UNIQUE (ticket_id, cycle_no), 
    CONSTRAINT fk_ticket_cycles_ticket_id FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_ticket_cycles_category_id FOREIGN KEY(category_id) REFERENCES ticket_categories (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_ticket_cycles_final_handler_id FOREIGN KEY(final_handler_id) REFERENCES users (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_ticket_cycles_2 ON ticket_cycles (final_handler_id, completed_at);

GO

CREATE INDEX ix_ticket_cycles_1 ON ticket_cycles (category_id, completed_at);

GO

CREATE INDEX ix_ticket_cycles_0 ON ticket_cycles (ticket_id, opened_at);

GO

CREATE TABLE ticket_resources (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    ticket_id VARCHAR(36) NOT NULL, 
    resource_id VARCHAR(36) NOT NULL, 
    relation_role VARCHAR(32) NOT NULL, 
    linked_by_user_id VARCHAR(36) NOT NULL, 
    CONSTRAINT pk_ticket_resources PRIMARY KEY (id), 
    CONSTRAINT uq_ticket_resources_0 UNIQUE (ticket_id, resource_id, relation_role), 
    CONSTRAINT fk_ticket_resources_ticket_id FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_ticket_resources_resource_id FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_ticket_resources_linked_by_user_id FOREIGN KEY(linked_by_user_id) REFERENCES users (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_ticket_resources_0 ON ticket_resources (resource_id, ticket_id);

GO

CREATE TABLE resource_files (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    resource_id VARCHAR(36) NOT NULL, 
    file_id VARCHAR(36) NOT NULL, 
    label NVARCHAR(128) NULL, 
    CONSTRAINT pk_resource_files PRIMARY KEY (id), 
    CONSTRAINT uq_resource_files_0 UNIQUE (file_id), 
    CONSTRAINT fk_resource_files_resource_id FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_resource_files_file_id FOREIGN KEY(file_id) REFERENCES file_objects (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_resource_files_0 ON resource_files (resource_id);

GO

CREATE TABLE contract_files (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    contract_id VARCHAR(36) NOT NULL, 
    file_id VARCHAR(36) NOT NULL, 
    CONSTRAINT pk_contract_files PRIMARY KEY (id), 
    CONSTRAINT uq_contract_files_0 UNIQUE (file_id), 
    CONSTRAINT fk_contract_files_contract_id FOREIGN KEY(contract_id) REFERENCES contracts (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_contract_files_file_id FOREIGN KEY(file_id) REFERENCES file_objects (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_contract_files_0 ON contract_files (contract_id);

GO

CREATE TABLE knowledge_versions (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    article_id VARCHAR(36) NOT NULL, 
    version_no INTEGER NOT NULL, 
    file_id VARCHAR(36) NOT NULL, 
    file_format VARCHAR(16) NOT NULL, 
    preview_file_id VARCHAR(36) NULL, 
    conversion_state VARCHAR(32) NOT NULL, 
    conversion_error_code VARCHAR(64) NULL, 
    page_count INTEGER NULL, 
    change_note NVARCHAR(1024) NULL, 
    search_text NTEXT NULL, 
    CONSTRAINT pk_knowledge_versions PRIMARY KEY (id), 
    CONSTRAINT uq_knowledge_versions_0 UNIQUE (article_id, version_no), 
    CONSTRAINT fk_knowledge_versions_article_id FOREIGN KEY(article_id) REFERENCES knowledge_articles (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_knowledge_versions_file_id FOREIGN KEY(file_id) REFERENCES file_objects (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_knowledge_versions_preview_file_id FOREIGN KEY(preview_file_id) REFERENCES file_objects (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_knowledge_versions_0 ON knowledge_versions (article_id, conversion_state);

GO

CREATE TABLE notifications (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    recipient_user_id VARCHAR(36) NOT NULL, 
    event_key VARCHAR(128) NOT NULL, 
    ticket_id VARCHAR(36) NULL, 
    resource_id VARCHAR(36) NULL, 
    title NVARCHAR(200) NOT NULL, 
    message_text NVARCHAR(1024) NULL, 
    read_at DATETIME2(3) NULL, 
    CONSTRAINT pk_notifications PRIMARY KEY (id), 
    CONSTRAINT uq_notifications_0 UNIQUE (recipient_user_id, event_key), 
    CONSTRAINT fk_notifications_recipient_user_id FOREIGN KEY(recipient_user_id) REFERENCES users (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_notifications_ticket_id FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_notifications_resource_id FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_notifications_0 ON notifications (recipient_user_id, read_at, created_at);

GO

CREATE TABLE import_batches (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    source_id VARCHAR(36) NOT NULL, 
    requested_by_user_id VARCHAR(36) NOT NULL, 
    original_filename NVARCHAR(256) NULL, 
    source_sha256 VARCHAR(64) NOT NULL, 
    template_version VARCHAR(32) NOT NULL, 
    batch_state VARCHAR(32) NOT NULL, 
    summary_json NTEXT NULL, 
    committed_at DATETIME2(3) NULL, 
    confirmed_by_user_id VARCHAR(36) NULL, 
    template_id VARCHAR(36) NOT NULL, 
    import_mode VARCHAR(32) NOT NULL, 
    error_result_file_id VARCHAR(36) NULL, 
    CONSTRAINT pk_import_batches PRIMARY KEY (id), 
    CONSTRAINT fk_import_batches_source_id FOREIGN KEY(source_id) REFERENCES data_sources (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_import_batches_requested_by_user_id FOREIGN KEY(requested_by_user_id) REFERENCES users (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_import_batches_confirmed_by_user_id FOREIGN KEY(confirmed_by_user_id) REFERENCES users (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_import_batches_template_id FOREIGN KEY(template_id) REFERENCES import_templates (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_import_batches_error_result_file_id FOREIGN KEY(error_result_file_id) REFERENCES file_objects (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_import_batches_0 ON import_batches (source_id, created_at);

GO

CREATE INDEX ix_import_batches_1 ON import_batches (batch_state);

GO

CREATE TABLE system_data_jobs (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    job_id VARCHAR(36) NULL, 
    operation VARCHAR(32) NOT NULL, 
    requested_by_user_id VARCHAR(36) NOT NULL, 
    confirmed_by_user_id VARCHAR(36) NULL, 
    package_file_id VARCHAR(36) NULL, 
    schema_version VARCHAR(32) NOT NULL, 
    source_engine VARCHAR(32) NOT NULL, 
    target_engine VARCHAR(32) NULL, 
    manifest_json NTEXT NULL, 
    operation_state VARCHAR(32) NOT NULL, 
    maintenance_confirmed BIT NOT NULL, 
    completed_at DATETIME2(3) NULL, 
    error_code VARCHAR(64) NULL, 
    CONSTRAINT pk_system_data_jobs PRIMARY KEY (id), 
    CONSTRAINT fk_system_data_jobs_job_id FOREIGN KEY(job_id) REFERENCES background_jobs (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_system_data_jobs_requested_by_user_id FOREIGN KEY(requested_by_user_id) REFERENCES users (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_system_data_jobs_confirmed_by_user_id FOREIGN KEY(confirmed_by_user_id) REFERENCES users (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_system_data_jobs_package_file_id FOREIGN KEY(package_file_id) REFERENCES file_objects (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_system_data_jobs_0 ON system_data_jobs (requested_by_user_id, created_at);

GO

CREATE INDEX ix_system_data_jobs_1 ON system_data_jobs (operation_state);

GO

CREATE TABLE device_identifiers (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    device_id VARCHAR(36) NOT NULL, 
    identifier_type VARCHAR(32) NOT NULL, 
    identifier_value VARCHAR(128) NOT NULL, 
    display_value NVARCHAR(200) NOT NULL, 
    CONSTRAINT pk_device_identifiers PRIMARY KEY (id), 
    CONSTRAINT uq_device_identifiers_0 UNIQUE (identifier_type, identifier_value), 
    CONSTRAINT fk_device_identifiers_device_id FOREIGN KEY(device_id) REFERENCES devices (resource_id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_device_identifiers_0 ON device_identifiers (device_id);

GO

CREATE TABLE device_interfaces (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    device_id VARCHAR(36) NOT NULL, 
    name NVARCHAR(128) NOT NULL, 
    interface_key VARCHAR(64) NOT NULL, 
    interface_type_code VARCHAR(64) NULL, 
    mac_address VARCHAR(17) NULL, 
    purpose NVARCHAR(512) NULL, 
    CONSTRAINT pk_device_interfaces PRIMARY KEY (id), 
    CONSTRAINT uq_device_interfaces_0 UNIQUE (device_id, interface_key), 
    CONSTRAINT fk_device_interfaces_device_id FOREIGN KEY(device_id) REFERENCES devices (resource_id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_device_interfaces_0 ON device_interfaces (device_id);

GO

CREATE TABLE device_endpoints (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    device_id VARCHAR(36) NOT NULL, 
    endpoint_type VARCHAR(32) NOT NULL, 
    address VARCHAR(253) NOT NULL, 
    port INTEGER NULL, 
    path NVARCHAR(512) NULL, 
    label NVARCHAR(128) NULL, 
    is_primary BIT NOT NULL, 
    CONSTRAINT pk_device_endpoints PRIMARY KEY (id), 
    CONSTRAINT fk_device_endpoints_device_id FOREIGN KEY(device_id) REFERENCES devices (resource_id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_device_endpoints_0 ON device_endpoints (device_id);

GO

CREATE TABLE subnets (
    resource_id VARCHAR(36) NOT NULL, 
    scope_id VARCHAR(36) NOT NULL, 
    vlan_id VARCHAR(36) NULL, 
    ip_version INTEGER NOT NULL, 
    network_address VARCHAR(45) NOT NULL, 
    prefix_length INTEGER NOT NULL, 
    cidr_key VARCHAR(49) NOT NULL, 
    purpose NVARCHAR(512) NULL, 
    CONSTRAINT pk_subnets PRIMARY KEY (resource_id), 
    CONSTRAINT uq_subnets_0 UNIQUE (scope_id, cidr_key), 
    CONSTRAINT fk_subnets_resource_id FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_subnets_scope_id FOREIGN KEY(scope_id) REFERENCES network_scopes (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_subnets_vlan_id FOREIGN KEY(vlan_id) REFERENCES vlans (resource_id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_subnets_0 ON subnets (vlan_id);

GO

CREATE TABLE wifi_vlan_bindings (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    wifi_id VARCHAR(36) NOT NULL, 
    vlan_id VARCHAR(36) NOT NULL, 
    binding_role VARCHAR(32) NOT NULL, 
    description NVARCHAR(512) NULL, 
    CONSTRAINT pk_wifi_vlan_bindings PRIMARY KEY (id), 
    CONSTRAINT uq_wifi_vlan_bindings_0 UNIQUE (wifi_id, vlan_id), 
    CONSTRAINT fk_wifi_vlan_bindings_wifi_id FOREIGN KEY(wifi_id) REFERENCES wifi_networks (resource_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_wifi_vlan_bindings_vlan_id FOREIGN KEY(vlan_id) REFERENCES vlans (resource_id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_wifi_vlan_bindings_0 ON wifi_vlan_bindings (vlan_id);

GO

CREATE TABLE ticket_events (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    ticket_id VARCHAR(36) NOT NULL, 
    cycle_id VARCHAR(36) NULL, 
    event_type VARCHAR(64) NOT NULL, 
    actor_user_id VARCHAR(36) NULL, 
    actor_name_snapshot NVARCHAR(128) NULL, 
    audience VARCHAR(16) NOT NULL, 
    body NTEXT NULL, 
    from_status VARCHAR(32) NULL, 
    to_status VARCHAR(32) NULL, 
    previous_assignee_id VARCHAR(36) NULL, 
    next_assignee_id VARCHAR(36) NULL, 
    occurred_at DATETIME2(3) NOT NULL, 
    request_id VARCHAR(64) NULL, 
    CONSTRAINT pk_ticket_events PRIMARY KEY (id), 
    CONSTRAINT fk_ticket_events_ticket_id FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_ticket_events_cycle_id FOREIGN KEY(cycle_id) REFERENCES ticket_cycles (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_ticket_events_actor_user_id FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_ticket_events_previous_assignee_id FOREIGN KEY(previous_assignee_id) REFERENCES users (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_ticket_events_next_assignee_id FOREIGN KEY(next_assignee_id) REFERENCES users (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_ticket_events_1 ON ticket_events (ticket_id, audience, occurred_at);

GO

CREATE INDEX ix_ticket_events_0 ON ticket_events (ticket_id, occurred_at, id);

GO

CREATE TABLE import_rows (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    batch_id VARCHAR(36) NOT NULL, 
    source_sheet NVARCHAR(80) NOT NULL, 
    source_row_key VARCHAR(64) NOT NULL, 
    entity_kind VARCHAR(32) NOT NULL, 
    source_external_key VARCHAR(128) NOT NULL, 
    normalized_json NTEXT NOT NULL, 
    proposal_json NTEXT NULL, 
    validation_json NTEXT NULL, 
    resolution_state VARCHAR(32) NOT NULL, 
    expected_version INTEGER NULL, 
    target_entity_kind VARCHAR(64) NULL, 
    target_entity_id VARCHAR(36) NULL, 
    CONSTRAINT pk_import_rows PRIMARY KEY (id), 
    CONSTRAINT uq_import_rows_0 UNIQUE (batch_id, source_sheet, source_row_key, entity_kind), 
    CONSTRAINT fk_import_rows_batch_id FOREIGN KEY(batch_id) REFERENCES import_batches (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_import_rows_0 ON import_rows (batch_id, resolution_state);

GO

CREATE TABLE circuit_endpoints (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    circuit_id VARCHAR(36) NOT NULL, 
    device_id VARCHAR(36) NULL, 
    interface_id VARCHAR(36) NULL, 
    ip_address VARCHAR(45) NULL, 
    prefix_length INTEGER NULL, 
    gateway VARCHAR(45) NULL, 
    label NVARCHAR(128) NULL, 
    is_primary BIT NOT NULL, 
    CONSTRAINT pk_circuit_endpoints PRIMARY KEY (id), 
    CONSTRAINT fk_circuit_endpoints_circuit_id FOREIGN KEY(circuit_id) REFERENCES circuits (resource_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_circuit_endpoints_device_id FOREIGN KEY(device_id) REFERENCES devices (resource_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_circuit_endpoints_interface_id FOREIGN KEY(interface_id) REFERENCES device_interfaces (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_circuit_endpoints_0 ON circuit_endpoints (circuit_id);

GO

CREATE INDEX ix_circuit_endpoints_1 ON circuit_endpoints (device_id);

GO

CREATE TABLE subnet_gateways (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    subnet_id VARCHAR(36) NOT NULL, 
    ip_address VARCHAR(45) NOT NULL, 
    gateway_role VARCHAR(32) NOT NULL, 
    device_id VARCHAR(36) NULL, 
    label NVARCHAR(128) NULL, 
    CONSTRAINT pk_subnet_gateways PRIMARY KEY (id), 
    CONSTRAINT uq_subnet_gateways_0 UNIQUE (subnet_id, ip_address), 
    CONSTRAINT fk_subnet_gateways_subnet_id FOREIGN KEY(subnet_id) REFERENCES subnets (resource_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_subnet_gateways_device_id FOREIGN KEY(device_id) REFERENCES devices (resource_id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_subnet_gateways_0 ON subnet_gateways (device_id);

GO

CREATE TABLE vpn_connections (
    resource_id VARCHAR(36) NOT NULL, 
    connection_type VARCHAR(32) NOT NULL, 
    remote_site_id VARCHAR(36) NULL, 
    remote_label NVARCHAR(128) NULL, 
    local_device_id VARCHAR(36) NULL, 
    local_interface_id VARCHAR(36) NULL, 
    circuit_id VARCHAR(36) NULL, 
    purpose NVARCHAR(512) NULL, 
    CONSTRAINT pk_vpn_connections PRIMARY KEY (resource_id), 
    CONSTRAINT fk_vpn_connections_resource_id FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_vpn_connections_remote_site_id FOREIGN KEY(remote_site_id) REFERENCES sites (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_vpn_connections_local_device_id FOREIGN KEY(local_device_id) REFERENCES devices (resource_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_vpn_connections_local_interface_id FOREIGN KEY(local_interface_id) REFERENCES device_interfaces (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_vpn_connections_circuit_id FOREIGN KEY(circuit_id) REFERENCES circuits (resource_id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_vpn_connections_0 ON vpn_connections (local_device_id);

GO

CREATE INDEX ix_vpn_connections_1 ON vpn_connections (circuit_id);

GO

CREATE TABLE ticket_attachments (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    event_id VARCHAR(36) NOT NULL, 
    file_id VARCHAR(36) NOT NULL, 
    preview_file_id VARCHAR(36) NULL, 
    CONSTRAINT pk_ticket_attachments PRIMARY KEY (id), 
    CONSTRAINT uq_ticket_attachments_0 UNIQUE (file_id), 
    CONSTRAINT fk_ticket_attachments_event_id FOREIGN KEY(event_id) REFERENCES ticket_events (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_ticket_attachments_file_id FOREIGN KEY(file_id) REFERENCES file_objects (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_ticket_attachments_preview_file_id FOREIGN KEY(preview_file_id) REFERENCES file_objects (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_ticket_attachments_0 ON ticket_attachments (event_id);

GO

CREATE TABLE data_quality_issues (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    resource_id VARCHAR(36) NULL, 
    import_row_id VARCHAR(36) NULL, 
    issue_code VARCHAR(64) NOT NULL, 
    field_name VARCHAR(64) NULL, 
    source_locator NVARCHAR(256) NULL, 
    message NVARCHAR(1024) NOT NULL, 
    issue_state VARCHAR(32) NOT NULL, 
    assigned_to_user_id VARCHAR(36) NULL, 
    resolved_at DATETIME2(3) NULL, 
    resolution_note NVARCHAR(1024) NULL, 
    CONSTRAINT pk_data_quality_issues PRIMARY KEY (id), 
    CONSTRAINT fk_data_quality_issues_resource_id FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_data_quality_issues_import_row_id FOREIGN KEY(import_row_id) REFERENCES import_rows (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_data_quality_issues_assigned_to_user_id FOREIGN KEY(assigned_to_user_id) REFERENCES users (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_data_quality_issues_1 ON data_quality_issues (resource_id);

GO

CREATE INDEX ix_data_quality_issues_0 ON data_quality_issues (issue_state, assigned_to_user_id);

GO

CREATE TABLE ticket_handling_segments (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    ticket_id VARCHAR(36) NOT NULL, 
    cycle_id VARCHAR(36) NOT NULL, 
    segment_no INTEGER NOT NULL, 
    handler_user_id VARCHAR(36) NULL, 
    started_at DATETIME2(3) NOT NULL, 
    ended_at DATETIME2(3) NULL, 
    duration_ms BIGINT NULL, 
    end_reason VARCHAR(32) NULL, 
    end_event_id VARCHAR(36) NULL, 
    handler_name_snapshot NVARCHAR(128) NULL, 
    CONSTRAINT pk_ticket_handling_segments PRIMARY KEY (id), 
    CONSTRAINT uq_ticket_handling_segments_0 UNIQUE (cycle_id, segment_no), 
    CONSTRAINT fk_ticket_handling_segments_ticket_id FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_ticket_handling_segments_cycle_id FOREIGN KEY(cycle_id) REFERENCES ticket_cycles (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_ticket_handling_segments_handler_user_id FOREIGN KEY(handler_user_id) REFERENCES users (id) ON DELETE NO ACTION, 
    CONSTRAINT fk_ticket_handling_segments_end_event_id FOREIGN KEY(end_event_id) REFERENCES ticket_events (id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_ticket_handling_segments_0 ON ticket_handling_segments (ticket_id, cycle_id);

GO

CREATE INDEX ix_ticket_handling_segments_1 ON ticket_handling_segments (handler_user_id, started_at);

GO

CREATE TABLE vpn_tunnels (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    connection_id VARCHAR(36) NOT NULL, 
    tunnel_number INTEGER NOT NULL, 
    tunnel_name NVARCHAR(128) NULL, 
    local_gateway VARCHAR(45) NULL, 
    remote_gateway VARCHAR(45) NULL, 
    registered_state VARCHAR(32) NOT NULL, 
    verified_at DATETIME2(3) NULL, 
    verified_by_user_id VARCHAR(36) NULL, 
    CONSTRAINT pk_vpn_tunnels PRIMARY KEY (id), 
    CONSTRAINT uq_vpn_tunnels_0 UNIQUE (connection_id, tunnel_number), 
    CONSTRAINT fk_vpn_tunnels_connection_id FOREIGN KEY(connection_id) REFERENCES vpn_connections (resource_id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_vpn_tunnels_0 ON vpn_tunnels (connection_id);

GO

CREATE TABLE vpn_routes (
    id VARCHAR(36) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    updated_at DATETIME2(3) NOT NULL, 
    created_by_user_id VARCHAR(36) NULL, 
    updated_by_user_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL, 
    is_archived BIT NOT NULL, 
    archived_at DATETIME2(3) NULL, 
    archived_by_user_id VARCHAR(36) NULL, 
    connection_id VARCHAR(36) NOT NULL, 
    direction VARCHAR(16) NOT NULL, 
    route_type VARCHAR(16) NOT NULL, 
    cidr_key VARCHAR(49) NULL, 
    route_key VARCHAR(64) NOT NULL, 
    description NVARCHAR(256) NULL, 
    CONSTRAINT pk_vpn_routes PRIMARY KEY (id), 
    CONSTRAINT uq_vpn_routes_0 UNIQUE (connection_id, direction, route_key), 
    CONSTRAINT fk_vpn_routes_connection_id FOREIGN KEY(connection_id) REFERENCES vpn_connections (resource_id) ON DELETE NO ACTION
);

GO

ALTER TABLE vpn_routes ADD CONSTRAINT fk_vpn_routes_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE tickets ADD CONSTRAINT fk_tickets_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE roles ADD CONSTRAINT fk_roles_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE vpn_routes ADD CONSTRAINT fk_vpn_routes_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE role_permission_sites ADD CONSTRAINT fk_role_permission_sites_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE roles ADD CONSTRAINT fk_roles_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE vpn_routes ADD CONSTRAINT fk_vpn_routes_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE device_identifiers ADD CONSTRAINT fk_device_identifiers_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE roles ADD CONSTRAINT fk_roles_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE device_identifiers ADD CONSTRAINT fk_device_identifiers_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE knowledge_recommendation_configs ADD CONSTRAINT fk_knowledge_recommendation_configs_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE resources ADD CONSTRAINT fk_resources_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE ticket_handling_segments ADD CONSTRAINT fk_ticket_handling_segments_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE device_identifiers ADD CONSTRAINT fk_device_identifiers_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE knowledge_recommendation_configs ADD CONSTRAINT fk_knowledge_recommendation_configs_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE ticket_handling_segments ADD CONSTRAINT fk_ticket_handling_segments_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE service_catalog ADD CONSTRAINT fk_service_catalog_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE knowledge_recommendation_configs ADD CONSTRAINT fk_knowledge_recommendation_configs_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE resources ADD CONSTRAINT fk_resources_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE contracts ADD CONSTRAINT fk_contracts_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE resource_files ADD CONSTRAINT fk_resource_files_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE resources ADD CONSTRAINT fk_resources_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE data_quality_issues ADD CONSTRAINT fk_data_quality_issues_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE departments ADD CONSTRAINT fk_departments_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE contracts ADD CONSTRAINT fk_contracts_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE service_catalog ADD CONSTRAINT fk_service_catalog_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE subnet_gateways ADD CONSTRAINT fk_subnet_gateways_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE data_quality_issues ADD CONSTRAINT fk_data_quality_issues_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE contracts ADD CONSTRAINT fk_contracts_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE departments ADD CONSTRAINT fk_departments_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE service_catalog ADD CONSTRAINT fk_service_catalog_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE subnet_gateways ADD CONSTRAINT fk_subnet_gateways_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE ticket_resources ADD CONSTRAINT fk_ticket_resources_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE departments ADD CONSTRAINT fk_departments_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE knowledge_articles ADD CONSTRAINT fk_knowledge_articles_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE data_quality_issues ADD CONSTRAINT fk_data_quality_issues_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE import_templates ADD CONSTRAINT fk_import_templates_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE subnet_gateways ADD CONSTRAINT fk_subnet_gateways_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE knowledge_articles ADD CONSTRAINT fk_knowledge_articles_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE dictionary_items ADD CONSTRAINT fk_dictionary_items_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE notifications ADD CONSTRAINT fk_notifications_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE role_permission_departments ADD CONSTRAINT fk_role_permission_departments_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE import_templates ADD CONSTRAINT fk_import_templates_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE resources ADD CONSTRAINT fk_resources_verified_by_user_id FOREIGN KEY(verified_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE knowledge_articles ADD CONSTRAINT fk_knowledge_articles_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE dictionary_items ADD CONSTRAINT fk_dictionary_items_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE notifications ADD CONSTRAINT fk_notifications_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE import_templates ADD CONSTRAINT fk_import_templates_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE permissions ADD CONSTRAINT fk_permissions_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE sites ADD CONSTRAINT fk_sites_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE dictionary_items ADD CONSTRAINT fk_dictionary_items_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE import_batches ADD CONSTRAINT fk_import_batches_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE sites ADD CONSTRAINT fk_sites_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE permissions ADD CONSTRAINT fk_permissions_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE resource_contracts ADD CONSTRAINT fk_resource_contracts_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE import_batches ADD CONSTRAINT fk_import_batches_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE sites ADD CONSTRAINT fk_sites_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE permissions ADD CONSTRAINT fk_permissions_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE ticket_categories ADD CONSTRAINT fk_ticket_categories_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE ticket_categories ADD CONSTRAINT fk_ticket_categories_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE device_interfaces ADD CONSTRAINT fk_device_interfaces_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE ticket_cycles ADD CONSTRAINT fk_ticket_cycles_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE contract_files ADD CONSTRAINT fk_contract_files_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE ticket_categories ADD CONSTRAINT fk_ticket_categories_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE device_interfaces ADD CONSTRAINT fk_device_interfaces_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE device_interfaces ADD CONSTRAINT fk_device_interfaces_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE ticket_cycles ADD CONSTRAINT fk_ticket_cycles_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE improvement_projects ADD CONSTRAINT fk_improvement_projects_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE circuit_endpoints ADD CONSTRAINT fk_circuit_endpoints_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE file_objects ADD CONSTRAINT fk_file_objects_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE background_jobs ADD CONSTRAINT fk_background_jobs_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE network_scopes ADD CONSTRAINT fk_network_scopes_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE circuit_endpoints ADD CONSTRAINT fk_circuit_endpoints_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE vendors ADD CONSTRAINT fk_vendors_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE vpn_tunnels ADD CONSTRAINT fk_vpn_tunnels_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE file_objects ADD CONSTRAINT fk_file_objects_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE improvement_projects ADD CONSTRAINT fk_improvement_projects_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE announcements ADD CONSTRAINT fk_announcements_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE user_roles ADD CONSTRAINT fk_user_roles_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE network_scopes ADD CONSTRAINT fk_network_scopes_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE vendors ADD CONSTRAINT fk_vendors_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE circuit_endpoints ADD CONSTRAINT fk_circuit_endpoints_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE vpn_tunnels ADD CONSTRAINT fk_vpn_tunnels_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE improvement_projects ADD CONSTRAINT fk_improvement_projects_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE background_jobs ADD CONSTRAINT fk_background_jobs_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE network_scopes ADD CONSTRAINT fk_network_scopes_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE announcements ADD CONSTRAINT fk_announcements_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE vendors ADD CONSTRAINT fk_vendors_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE vpn_tunnels ADD CONSTRAINT fk_vpn_tunnels_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE site_aliases ADD CONSTRAINT fk_site_aliases_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE system_settings ADD CONSTRAINT fk_system_settings_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE announcements ADD CONSTRAINT fk_announcements_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE site_aliases ADD CONSTRAINT fk_site_aliases_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE knowledge_versions ADD CONSTRAINT fk_knowledge_versions_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE system_settings ADD CONSTRAINT fk_system_settings_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE vpn_tunnels ADD CONSTRAINT fk_vpn_tunnels_verified_by_user_id FOREIGN KEY(verified_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE site_aliases ADD CONSTRAINT fk_site_aliases_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE wifi_vlan_bindings ADD CONSTRAINT fk_wifi_vlan_bindings_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE knowledge_versions ADD CONSTRAINT fk_knowledge_versions_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE import_rows ADD CONSTRAINT fk_import_rows_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE system_settings ADD CONSTRAINT fk_system_settings_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE system_data_jobs ADD CONSTRAINT fk_system_data_jobs_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE locations ADD CONSTRAINT fk_locations_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE import_rows ADD CONSTRAINT fk_import_rows_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE system_data_jobs ADD CONSTRAINT fk_system_data_jobs_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE locations ADD CONSTRAINT fk_locations_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE users ADD CONSTRAINT fk_users_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE locations ADD CONSTRAINT fk_locations_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE users ADD CONSTRAINT fk_users_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE knowledge_categories ADD CONSTRAINT fk_knowledge_categories_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE data_sources ADD CONSTRAINT fk_data_sources_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE users ADD CONSTRAINT fk_users_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE device_endpoints ADD CONSTRAINT fk_device_endpoints_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE knowledge_categories ADD CONSTRAINT fk_knowledge_categories_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE role_permissions ADD CONSTRAINT fk_role_permissions_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE ticket_attachments ADD CONSTRAINT fk_ticket_attachments_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE device_endpoints ADD CONSTRAINT fk_device_endpoints_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE knowledge_categories ADD CONSTRAINT fk_knowledge_categories_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE data_sources ADD CONSTRAINT fk_data_sources_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE data_sources ADD CONSTRAINT fk_data_sources_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE device_endpoints ADD CONSTRAINT fk_device_endpoints_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE external_links ADD CONSTRAINT fk_external_links_created_by_user_id FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE tickets ADD CONSTRAINT fk_tickets_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE external_links ADD CONSTRAINT fk_external_links_updated_by_user_id FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

ALTER TABLE external_links ADD CONSTRAINT fk_external_links_archived_by_user_id FOREIGN KEY(archived_by_user_id) REFERENCES users (id) ON DELETE NO ACTION;

GO

INSERT INTO alembic_version (version_num) OUTPUT inserted.version_num VALUES ('0001_business');

GO

COMMIT;

GO

