import logging
import os
from datetime import datetime, timedelta

import boto3
import pandas as pd
from airflow import DAG
from airflow.operators.python import PythonOperator
from botocore.exceptions import ClientError
from decouple import config
from sqlalchemy import create_engine
from sqlalchemy.sql import text

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d',
    level=logging.INFO,
    filemode="a"
    )
logger = logging.getLogger(__name__)

default_args = {
    'retries': 5,
    'retry_delay': timedelta(minutes=5)
}

# Instance directories
current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))

# Global variables used in transform functions
columns_types = {
                'university': 'string',
                'career': 'string',
                'inscription_date': 'string',
                'first_name': 'string',
                'last_name': 'string',
                'gender': 'category',
                'age': 'int64',
                'postal_code': 'string',
                'location': 'string',
                'email': 'string'
                }
delete_abreviations = {
                    'mr.': '',
                    'dr.': '',
                    'mrs.': '',
                    'ms.': '',
                    'md': '',
                    'dds': '',
                    'jr.': '',
                    'dvm': '',
                    'phd': ''
                }
sort_columns = [
                'university',
                'career',
                'inscription_date',
                'first_name',
                'last_name',
                'gender',
                'age',
                'postal_code',
                'location',
                'email'
                ]


def calculate_age(born, born_datefmt):
    """Calculates age from date of birth. Returns age as integer
    Args:
        born (str): formatted date in string type.
        born_datefmt (str): input date format to be interpreted by function to read data. e.g.: %y-%b-%d. for 90-Jan-01.
    """
    born = datetime.strptime(born, born_datefmt)
    today = datetime.today()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    if age < 0:
        age += 100
    return age


def extract_data(sql, csv):
    """Extact data. Connection to DB, execute SQL query and export to CSV.
    Args:
        sql (str): Name of SQL script to be executed in '../sql/' directory.
        csv (str): Name of CSV output to be generated in '../files/' directory (creates it automatically if not exists).
    """

    # Database Connection
    db_user = config('DB_USER')
    db_password = config('DB_PASSWORD')
    db_host = config('DB_HOST')
    db_port = config('DB_PORT')
    db_database = config('DB_DATABASE')
    url = f'postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_database}'

    # Instance directories
    current_dir = os.path.abspath(os.path.dirname(__file__))
    parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))

    # Execute SQl query
    file_path = f'{parent_dir}/sql/{sql}'
    with open(file_path, 'r') as file:
        engine = create_engine(url, encoding='utf8')
        con = engine.connect()
        query = text(file.read())
        df = pd.read_sql(query, con)
        logger.info(sql + csv)
        if not os.path.exists(f'{parent_dir}/files'):
            os.makedirs(f'{parent_dir}/files')
        df.to_csv(f'{parent_dir}/files/{csv}', encoding='utf-8')
        con.close()


def transform_cine_data(csv, txt, born_datefmt):
    """Function for transform data from Universidad del Cine previously extracted from Postgres database.
        - Read previously extracted csv
        - Import postal code asset csv
        - Transform data to make a .txt output prepared to be loaded to S3
    Args:
        csv (str): input filename, extracted data
        txt (str): output filename, transformed data
        born_datefmt (str): date format used in calculate_age function
    """
    # Instance directories
    current_dir = os.path.abspath(os.path.dirname(__file__))
    parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))

    # Read extracted data and postal code asset. Merge in unique dataset
    df_cine = pd.read_csv(f'{parent_dir}/files/{csv}', encoding='utf-8')
    df_cp = pd.read_csv(f'{parent_dir}/files/codigos_postales.csv', encoding='utf-8')
    df_cp.rename(columns={'localidad': 'location', 'codigo_postal': 'postal_code'}, inplace=True)
    df_cp['location'] = df_cp['location'].apply(lambda x: x.lower().strip(' '))

    # Transform data from Universidad del Cine
    df_cine = df_cine.drop(['Unnamed: 0'], axis=1)
    df_cine = df_cine.convert_dtypes()
    for column in df_cine.columns:
        if column in ['university', 'career', 'name', 'location']:
            df_cine[column] = df_cine[column].apply(lambda x: x.lower().replace('-', ' ').strip(' '))
        elif column == 'email':
            df_cine[column] = df_cine[column].apply(lambda x: x.lower().strip(' '))
        elif column == 'age':
            df_cine['age'] = df_cine['age'].apply(lambda x: calculate_age(x, born_datefmt))
        elif column == 'gender':
            df_cine['gender'] = df_cine['gender'].apply(lambda x: x.lower()
                                                                   .replace('m', 'male')
                                                                   .replace('f', 'female')
                                                                   .strip(' '))
        elif column == 'inscription_date':
            df_cine['inscription_date'] = df_cine['inscription_date'].apply(lambda x: datetime.strftime(
                                                                                      datetime.strptime(x, '%d-%m-%Y'),
                                                                                      '%Y-%m-%d'))

    # Merge postal codes to Universidad del Cine DataFrame
    df_cine = df_cine.merge(df_cp, on='location', how='left')

    # Delete abreviations in name column
    for abreviation, blank in delete_abreviations.items():
        df_cine['name'] = df_cine['name'].apply(lambda x: x.replace(abreviation, blank))

    # Split name into first name and last name
    df_cine['name'] = df_cine['name'].apply(lambda x: x.strip(' '))
    df_cine['name'] = df_cine['name'].astype('string')
    df_cine['first_name'] = df_cine['name'].apply(lambda x: x.split(' ')[0])
    df_cine['last_name'] = df_cine['name'].apply(lambda x: x.split(' ')[-1])
    df_cine = df_cine.drop(['name'], axis=1)

    # Set column types
    for column, type_column in columns_types.items():
        df_cine[column] = df_cine[column].astype(type_column)

    # Sorting columns
    df_cine = df_cine[sort_columns]

    return df_cine.to_csv(f'{parent_dir}/files/{txt}', encoding='utf-8', index=False, sep='\t')


def transform_uba_data(csv, txt, born_datefmt):
    """Function for transform data from Universidad de Buenos Aires previously extracted from Postgres database.
        - Read previously extracted csv
        - Import postal code asset csv
        - Transform data to make a .txt output prepared to be loaded to S3
    Args:
        csv (str): input filename, extracted data
        txt (str): output filename, transformed data
        born_datefmt (str): date format used in calculate_age function
    """
    # Instance directories
    current_dir = os.path.abspath(os.path.dirname(__file__))
    parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))

    # Read extracted data and postal code asset. Merge in unique dataset
    df_uba = pd.read_csv(f'{parent_dir}/files/{csv}', encoding='utf-8')
    df_cp = pd.read_csv(f'{parent_dir}/files/codigos_postales.csv', encoding='utf-8')
    df_cp.rename(columns={'localidad': 'location', 'codigo_postal': 'postal_code'}, inplace=True)
    df_cp['location'] = df_cp['location'].apply(lambda x: x.lower().strip(' '))

    # Transform data from Universidad de Buenos Aires
    df_uba = df_uba.drop(['Unnamed: 0'], axis=1)
    df_uba = df_uba.convert_dtypes()
    for column in df_uba.columns:
        if column in ['university', 'career', 'name', 'location']:
            df_uba[column] = df_uba[column].apply(lambda x: x.lower().replace('-', ' ').strip(' '))
        elif column == 'email':
            df_uba[column] = df_uba[column].apply(lambda x: x.lower().strip(' '))
        elif column == 'age':
            df_uba['age'] = df_uba['age'].apply(lambda x: calculate_age(x, born_datefmt))
        elif column == 'gender':
            df_uba['gender'] = df_uba['gender'].apply(lambda x: x.replace('m', 'male')
                                                                 .replace('f', 'female')
                                                                 .strip(' '))
        elif column == 'inscription_date':
            df_uba['inscription_date'] = df_uba['inscription_date'].apply(lambda x: datetime.strftime(
                                                                                    datetime.strptime(x, '%d-%b-%y'),
                                                                                    '%Y-%m-%d'))

    # Merge postal codes to Universidad de Buenos Aires DataFrame
    df_uba = df_uba.merge(df_cp, on='postal_code', how='left')

    # Delete abreviations in name column
    for abreviation, blank in delete_abreviations.items():
        df_uba['name'] = df_uba['name'].apply(lambda x: x.replace(abreviation, blank))

    # Split name into first name and last name
    df_uba['name'] = df_uba['name'].apply(lambda x: x.strip(' '))
    df_uba['name'] = df_uba['name'].astype('string')
    df_uba['first_name'] = df_uba['name'].apply(lambda x: x.split(' ')[0])
    df_uba['last_name'] = df_uba['name'].apply(lambda x: x.split(' ')[-1])
    df_uba = df_uba.drop(['name'], axis=1)

    # Set column types
    for column, type_column in columns_types.items():
        df_uba[column] = df_uba[column].astype(type_column)

    # Sorting columns
    df_uba = df_uba[sort_columns]

    return df_uba.to_csv(f'{parent_dir}/files/{txt}', encoding='utf-8', index=False, sep='\t')


def load_data(file_name, object_name=None):
    """Upload a file to an S3 bucket
    Args:
        file_name (str): File to upload
        object_name (str): S3 object name. If not specified then file_name is used
    return True if file was uploaded, else False
    """

    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = os.path.basename(file_name)

    # Upload the file
    s3_client = boto3.client(
                            's3',
                            aws_access_key_id=config('AWS_PUBLIC_KEY'),
                            aws_secret_access_key=config('AWS_SECRET_KEY')
                        )
    try:
        s3_client.upload_file(f'{parent_dir}/files/{file_name}', config('AWS_BUCKET_NAME'), object_name)
    except ClientError as e:
        logging.error(e)
        return False
    return True


with DAG(
    'universities_etl_data',
    default_args=default_args,
    description='DAG for processing data from Universidad Del Cine and Universidad De Buenos Aires',
    schedule_interval=timedelta(hours=1),
    start_date=datetime(2022, 3, 20)
) as dag:
    
    # Extract data with SQL query - Python operator
    extract_uba = PythonOperator(
                    task_id='extract_uba',
                    python_callable=extract_data,
                    op_kwargs={
                        'sql': 'query_uba.sql',
                        'csv': 'extract_uba.csv'
                        }
                    )
    extract_cine = PythonOperator(
                    task_id='extract_cine',
                    python_callable=extract_data,
                    op_kwargs={
                        'sql': 'query_cine.sql',
                        'csv': 'extract_cine.csv'
                        }
                    )

    # Transform data with Pandas - Python operator
    transform_uba = PythonOperator(
                    task_id='transform_uba',
                    python_callable=transform_uba_data,
                    op_kwargs={
                        'csv': 'extract_uba.csv',
                        'txt': 'transform_uba.txt',
                        'born_datefmt': '%y-%b-%d'
                        }
                    )
    transform_cine = PythonOperator(
                    task_id='transform_cine',
                    python_callable=transform_cine_data,
                    op_kwargs={
                        'csv': 'extract_cine.csv',
                        'txt': 'transform_cine.txt',
                        'born_datefmt': '%d-%m-%Y'
                        }
                    )

    # Load data to S3 - S3 operator
    load_uba = PythonOperator(
                    task_id='load_uba',
                    python_callable=load_data,
                    op_kwargs={
                        'file_name': 'transform_uba.txt'
                        }
                    )
    load_cine = PythonOperator(
                    task_id='load_cine',
                    python_callable=load_data,
                    op_kwargs={
                        'file_name': 'transform_cine.txt'
                        }
                    )


    [extract_uba >> transform_uba >> load_uba, extract_cine >> transform_cine >> load_cine]
