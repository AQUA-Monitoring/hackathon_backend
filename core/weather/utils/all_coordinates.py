import os, geopandas
from shapely.geometry import Point

from core.weather.utils.process_weather import process_weather

def all_coordinates():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    geojson = os.path.dirname(BASE_DIR, "weather", "fixtures", "neighborhoods.geojson")
    step = 0.01

    gdf = geopandas.read_file(geojson)
    poligono = gdf.unary_all

    lon_min, lat_min, lon_max, lat_max = poligono.bounds
    lat = float(lat_min)
    lon = float(lon_min)

    while lat < float(lat_max):
        while lon < float(lon_max):
            ponto = Point(lat, lon)
            if poligono.contains(ponto):
                weather = process_weather(lat, lon)
            lon += step
        lat += step

    return weather