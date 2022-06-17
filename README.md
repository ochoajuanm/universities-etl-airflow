# Universities ETL data

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)
![Apache Airflow](https://img.shields.io/badge/Apache%20Airflow-017CEE?style=for-the-badge&logo=Apache%20Airflow&logoColor=white)
![Postgres](https://img.shields.io/badge/postgres-%23316192.svg?style=for-the-badge&logo=postgresql&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-%23FF9900.svg?style=for-the-badge&logo=amazon-aws&logoColor=white)
![Pandas](https://img.shields.io/badge/pandas-%23150458.svg?style=for-the-badge&logo=pandas&logoColor=white)

## Un proceso ETL orquestado con Apache Airflow

Este es un proyecto trabajado en [Alkemy](https://www.alkemy.org/), donde el objetivo es realizar extracción de la información de distintas universidades sobre las inscripciones de alumnos, transformarla para que puedan analizar la información relevante y tomar directrices en cuanto a qué carreras universitarias requieren programa de becas, qué planes de estudios tienen adhesión, entre otros.

## Extract

La extracción de los datos se realiza mediante consultas SQL con `sqlalchemy` en Python a una base de datos en Amazon RDS y exportados a archivos .csv con `pandas`

## Transform

Una vez extraídos los datos "crudos" procedemos a realizar transformaciones con la librería `pandas` de Python, y los exportammos mediante archivos .txt

## Load

La carga será automatizada levantando esos archivos con la librería `boto3`, y mediante la conexión provista serán cargados a un bucket de Amazon S3

## Automatización

Todo el proceso será orquestado mediante un DAG de Apache Airflow donde en todas sus etapas se utilizarán Python Operators.

## Deploy

Adicional: Se implementarán contenedores de Docker con el fin de simplificar tanto la instalación como configuración inicial y ejecución de todos los servicios que componen a Apache Airflow (webserver, worker, scheduler, redis y postgres)

## Instalación

### Instalación dentro de un virtualenv

```bash
git clone this_repo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Luego se deben seguir los pasos indicados en la documentación oficial de Apache Airflow https://airflow.apache.org/docs/apache-airflow/stable/installation/installing-from-pypi.html

### Deploy de contenedores (Recomendado, previamente instalando Docker)

```bash
# Build de imagen personalizada con dependencias de este proyecto a partir de la imagen de airflow
# Utiliza el Dockerfile para personalizar la imagen
docker build -t universities-airflow .

# Levantamos todos los servicios con esta imagen personalizada
docker-compose up -d
```
