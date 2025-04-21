import requests
from django.shortcuts import render
from django.core.cache import cache
import spacy
from datetime import datetime
import pytz
import pandas as pd
import plotly.express as px

nlp = spacy.load('ru_core_news_md')

# Конвертируем время в формат unixtime
def convert_to_unix_timestamp(date_string, time_string):
    datetime_string = f"{date_string} {time_string}"
    dt = datetime.strptime(datetime_string, '%Y-%m-%d %H:%M')
    timezone = pytz.timezone('Europe/Moscow')
    dt_with_tz = timezone.localize(dt)
    unix_timestamp = int(dt_with_tz.timestamp())
    return unix_timestamp

# Запрос на VK
def fearch_posts(query, count, token, start_time, end_time):
    url = f'https://api.vk.com/method/newsfeed.search?q={query}&count={count}&access_token={token}&v=5.131'
    
    if start_time:
        url += f'&start_time={start_time}'
    if end_time:
        url += f'&end_time={end_time}'

    response = requests.get(url)
    return response.json()

# Обработка текстовой информации постов
def process_posts(posts, query):
    query_doc = nlp(query)
    posts_with_similarity = []
    post_texts = [post['text'] for post in posts if 'text' in post]
    post_docs = list(nlp.pipe(post_texts))

    for post, post_doc in zip(posts, post_docs):
        similarity = query_doc.similarity(post_doc)
        posts_with_similarity.append((post, similarity))

    posts_with_similarity.sort(key=lambda x: x[1], reverse=True)
    return [post for post, _ in posts_with_similarity]

# Получение геоданных и текста постов
def marker_map(posts):
    geo_data = []
    x=0
    for post in posts:
        x+=1
        if 'geo' in post:
            lat = post['geo']['place']['latitude']
            lon = post['geo']['place']['longitude']
            title = post['geo']['place']['title']
            geo_data.append({
                'latitude': lat,
                'longitude': lon,
                'text': title  # Добавляем текст поста
            })
    print(x)
    return geo_data

def generate_statistics(geo_data):
    if not geo_data:
        return pd.DataFrame()  # Возвращаем пустой DataFrame, если нет данных

    df_geo_data = pd.DataFrame(geo_data)
    statistics = df_geo_data.groupby('text').size().reset_index(name='count')
    statistics = statistics.sort_values(by='count', ascending=False)
    return statistics

# Поиск постов и кэширования
def search_posts(request):
    posts = []
    geo_data = []

    if 'query' in request.GET:
        query = request.GET['query']
        token = '5a501d085a501d085a501d08f05977deeb55a505a501d083ddfbbe3c4619fe65c0e2b1b'  # Замените на ваш токен доступа
        count = request.GET['count']
        start_time = request.GET['start_time']

        if start_time:
            date_string, time_string = start_time.split('T')
            start_time_unix = convert_to_unix_timestamp(date_string, time_string)
        else:
            start_time_unix = None

        
        end_time_unix = start_time_unix + 86400 

        cache_key = f'search_posts_{query.replace(" ", "_")}_{count}_{start_time_unix}_{end_time_unix}'
        cached_data = cache.get(cache_key)

        if cached_data:
            data = cached_data
        else:
            data = fearch_posts(query, count, token, start_time_unix, end_time_unix)
            cache.set(cache_key, data, timeout=60*5)

        if 'response' in data:
            posts = data['response']['items']
            posts = process_posts(posts, query)
            geo_posts = data['response']['items']
            geo_data = marker_map(geo_posts)

    # Проверяем содержимое geo_data перед созданием DataFrame
    if geo_data:
        df_geo_data = pd.DataFrame(geo_data)

        # Создаем карту с помощью Plotly
        fig = px.scatter_geo(df_geo_data,
                            lat='latitude',
                            lon='longitude',
                            hover_name='text', 

                             )
        
        fig.update_layout(
            geo=dict(
                showland=True,
                showlakes = True,
                showcountries = True,
                showocean = True,
                countrywidth = 0.5,
                lakecolor = 'rgb(0, 255, 255)',
                oceancolor = 'rgb(0, 255, 255)',
                landcolor='lightgreen',
                countrycolor='black',
                projection = dict(
                    type = 'orthographic',
                )
            ),
            width = 850,
            height = 600,
        )

        graph_html = fig.to_html(full_html=False)
    else:
        graph_html = None  # Если нет данных для отображения
        
    statistics = generate_statistics(geo_data)

    return render(request, 'posts/search.html', {'posts': posts, 'graph_html': graph_html})
