from alembic import context
from portal.database import metadata,settings,database_url,make_engine

if context.is_offline_mode():
    context.configure(url=database_url(settings()),target_metadata=metadata,literal_binds=True)
    with context.begin_transaction():context.run_migrations()
else:
    engine=make_engine(database_url(settings()))
    try:
        with engine.connect() as connection:
            context.configure(connection=connection,target_metadata=metadata,compare_type=True)
            with context.begin_transaction():context.run_migrations()
    finally:
        engine.dispose()
