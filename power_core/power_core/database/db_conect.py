import os
import psycopg



import logging
logger = logging.getLogger(__name__)


# AS dataframe
import sqlalchemy as sql
import pandas as pd
from urllib.parse import quote_plus

def connect_to_db_pandas():
    # connection_uri = os.environ.get("PG_DATABASE_URI")

    connection_uri = []
    try:
        user = os.environ.get("PG_USER")
        password = os.environ.get("PG_PASS")
        safe_password = quote_plus(password)
        connection_uri = f"postgresql+psycopg://{user}:{safe_password}@localhost:5432/forest_rides_db"
        logger.info(f"Cn {connection_uri}")
        db_engine = sql.create_engine(connection_uri)
        raw_data = pd.read_sql_table("pressure", db_engine)
        return raw_data
    except:
        logger.error(f"Error connecting to PostgreSQL database: {connection_uri}")


# as table data
def connect_to_db():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg.connect(
            # Local testing uses 'localhost'. Cloud Run uses '10.128.x.x'.
            host=os.environ.get("PG_HOST"),
            port=os.environ.get("PG_PORT", 5432),
            dbname=os.environ.get("PG_DATABASE"),
            user=os.environ.get("PG_USER"),
            password=os.environ.get("PG_PASS")
        )
        conn.autocommit = True
        return conn
    except psycopg.OperationalError as e:
        logger.error(f"Error connecting to database: {e}")
        raise ConnectionError("Failed to connect to the PostgreSQL database.") from e

def get_user_by_id(some_data):
    """Fetches a user from the database by their ID."""
    conn = None
    try:
        conn = connect_to_db()
        # 'with' statement ensures the cursor is automatically closed
        with conn.cursor() as cur:
            # Use %s as a placeholder for parameters to prevent SQL injection
            cur.execute("SELECT * FROM pressure WHERE pulse = %s", (some_data,))
            user_data = cur.fetchone()  # Fetches the first matching row

            if user_data:
                logger.info("Found data")
                return user_data
            else:
                logger.warning(f"Data {some_data} not found.")
                return None
    except Exception as e:
        logger.error(f"An error occurred while fetching user: {e}")
        raise
    finally:
        if conn:
            # Always close the connection when you're done with it
            conn.close()


def add_new_user(username, email):
    """Adds a new user to the database and returns the new user's ID."""
    sql = "INSERT INTO users (username, email) VALUES (%s, %s) RETURNING id;"
    conn = None
    try:
        conn = connect_to_db()
        with conn.cursor() as cur:
            cur.execute(sql, (username, email))
            # Fetch the returned ID from the INSERT statement
            new_user_id = cur.fetchone()[0]
            logger.info(f"Added new user with ID: {new_user_id}")
            return new_user_id
    except Exception as e:
        logger.error(f"Error adding new user: {e}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    from gcp_actions.common_utils.handle_logs import run_handle_logs
    from gcp_actions.common_utils.local_runner import check_cloud_or_local_run
    run_handle_logs()
    check_cloud_or_local_run()

    # conn1 = connect_to_db()
    #
    # all_records = get_user_by_id(61)
    # print(all_records)
    # for record in all_records:
    #     print(record)
    sss = connect_to_db_pandas()
    print(sss)

