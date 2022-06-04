# ETL pipeline to process universities data

An ETL process orchested with Apache Airflow

git clone this_repo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

docker build -t universities-airflow .
docker compose up -d