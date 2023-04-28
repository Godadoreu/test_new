# This is a sample Python script.
from prefect import Flow,task
import psycopg2
from datetime import datetime
import pickle
import hashlib
from prefect.blocks.system import String
# github
@task
def get_md5(data):
    '''Функция для расчитывания уникального хэш ключа'''
    d = pickle.dumps(data)
    return hashlib.md5(d).hexdigest()
@task
def convert(data):
    '''Преобразование данных под нужный формат в DWH'''
    y = list(data)
    for x in range(len(y)):
        if isinstance(y[x], bool):
            y[x] = int(y[x])
    data = tuple(y)
    return data
@Flow
def main():
    # Use a breakpoint in the code line below to debug your script.
    try:
        # забираем все нужные параметры для подключения к базе с помощью блоков в префекте
        string_block = String.load("postgres2")
        result = string_block.value.split(',')
        # configs for local database
        database_name = result[0]
        source_user = result[1]
        source_password = result[2]
        source_host = result[3]
        # подключение
        conn = psycopg2.connect(database=database_name, user = source_user, password= source_password, host=source_host, port='5432')
        source_schema = result[4]
        source_table = result[5]
        # информация о колонках
        sql = "SELECT column_name FROM information_schema.columns WHERE table_schema = '" + 'test_data' + "' AND table_name = '" + source_table + "';"
        cursor = conn.cursor()
        cursor.execute(sql)
        data = cursor.fetchall()
        column_data = [x[0] for x in data]
        list_table_data = ','.join(column_data)
        # для настройки инкрементальной выгрузки
        datetime1 = "select coalesce(max(deleted_at),'1970-01-01') from " + result[6] + '.' + result[7]
        datetime2 = "select coalesce(max(updated_at),'1970-01-01') from " + result[6] + '.' + result[7]
        datetime3 = "select coalesce(max(created_at),'1970-01-01') from " + result[6] + '.' + result[7]
        cursor.execute(datetime1)
        date1 = cursor.fetchone()[0]
        cursor.execute(datetime2)
        date2 = cursor.fetchone()[0]
        cursor.execute(datetime3)
        date3 = cursor.fetchone()[0]
        # забор только новых записей
        info_sql = "Select * from " + source_schema +'.' + source_table + ' where deleted_at > timestamp %s' + ' or updated_at > timestamp %s' + \
            " or created_at > timestamp %s"
        # двх в которую будем грузить данные
        target_schema = result[6]
        target_table = result[7]
        # уникальный индекс по которому будем отсекать по дублям
        unique_index = result[8]
        cursor.execute(info_sql, (date1,date2,date3))
        insert_data = cursor.fetchall()
        # выгрузка новых записей
        for x in insert_data:
            value_replace = ','.join(['%s' for x in range(len(column_data))])
            date = datetime.now()
            # уникальный хэш
            md5 = get_md5(x)
            # системные поля
            sys_tuple = (md5,date)
            # добавление с основными поля
            insert_tuple = x + sys_tuple
            # конвертирование полей под нужный формат
            insert_tuple = convert(insert_tuple)
            # запрос для выгрузки в двх с учетом апдейтов и дублей
            sql = "INSERT INTO " + target_schema + "." + target_table + "(" + list_table_data + ")" + \
                  " VALUES (" + value_replace + ")" + "ON CONFLICT ( " + unique_index + ") DO UPDATE  SET (" + \
                  list_table_data + ") = (" + value_replace + ")"
            cursor.execute(sql, insert_tuple + insert_tuple)
            conn.commit()
        conn.commit()
    except (Exception, psycopg2.Error) as error:
        print(error)
    finally:
    # closing database connection.
        if conn:
            cursor.close()
            conn.close()
            print("PostgreSQL connection is closed")
main()
