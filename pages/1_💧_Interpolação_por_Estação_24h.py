import streamlit as st
import pandas as pd 
import plotly.express as px
import geopandas as gpd
from osgeo import gdal, ogr, osr
import requests
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import functions.geodados as geodados

# Loading Environment Variables
load_dotenv()


st.set_page_config(layout="wide")
st.title('Interpolação por Estação - IDW contínuo')

st.sidebar.image('data/logo.png')

# Recebe o valor digitado no `st.text_input` como entrada do usuário
excluir_prefixos = st.text_input(
    "Digite os prefixos das estações a serem excluídas para remoção de outliers.",
    value="",  # valor inicial vazio
    placeholder="Exemplo: IAC-Ibitinga - SP, 350320801A",
    help="Digite os prefixos separados por vírgula. Consulte os prefixos no site do SIBH."
).strip()

# Processa a lista de prefixos inseridos, se houver algum
if excluir_prefixos:
    prefixos_para_excluir = [prefixo.strip() for prefixo in excluir_prefixos.split(",")]
    st.write(f"Prefixos a serem excluídos: {prefixos_para_excluir}")
else:
    st.write("Nenhum prefixo excluído.")

# Sliders para ajustar parâmetros da interpolação IDW
st.subheader("Parâmetros da Interpolação IDW")

power = st.slider(
    "Power (potência da interpolação)",
    min_value=0.0, max_value=5.0, value=2.0, step=0.1,
    help="A potência determina o peso da distância na interpolação."
)

smoothing = st.slider(
    "Smoothing (suavização)",
    min_value=0.0, max_value=1.0, value=0.1, step=0.01,
    help="A suavização reduz a variabilidade na interpolação. Valores maiores tornam o mapa mais suave e menos influenciado por variações locais. Maior generalização"
)

radius = st.slider(
    "Radius (raio de influência)",
    min_value=0.0, max_value=5.0, value=0.5, step=0.1,
    help="O raio determina a distância máxima em torno de cada ponto para considerar na interpolação. Valores maiores aumentam a área de influência. 10km de buffer corresponde a 0,1"
)

upload_to_geonode = st.checkbox("Salvar no Geodados?", value=False, help="Selecione caso queira salvar o resultado no Geodados \n(https://geodados.daee.sp.gov.br/#/)")

# URL and user inputs for testing
hoje = datetime.now()
hoje_format = hoje.strftime('%Y-%m-%d')
ontem = hoje - timedelta(days=1)
ontem_format = ontem.strftime('%Y-%m-%d')

date_time_id = ontem.strftime("%Y%m%d%H%M")

url = f'https://cth.daee.sp.gov.br/sibh/api/v1/measurements/last_hours_events?hours=24&from_date={hoje_format}T07%3A00&show_all=true'
titulo = f"Acumulado de chuvas 24H\n07:00h de {ontem_format} às 07h de {hoje_format}"

# Definição dos limites
bounds = [0, 1, 2, 5, 7, 10, 15, 20, 25, 30, 40, 50, 75, 100, 250]
bounds2 = [0, 5, 10, 15, 20, 30, 40, 50, 100, 125, 150, 200, 250, 300, 350]

# Dicionário de opções
options = {
    "Opção recomendada para períodos secos": bounds,
    "Opção recomendada para períodos chuvosos": bounds2,
}


# Interface do Streamlit para seleção do intervalo
selected_option = st.radio(
    "Selecione o intervalo de cores",
    list(options.keys()),  # Mostra as opções do dicionário
)

# Obter o intervalo selecionado com base na escolha
selected_bounds = options[selected_option]

# Exibir o intervalo selecionado
st.write("Intervalo selecionado:", str(selected_bounds))


# Define the function for displaying table and interactive chart
def exibir_graficos_tabela(url, excluir_prefixos):
    # Fetching data from API
    response = requests.get(url)
    data = response.json()

    # Extracting station details and precipitation values
    stations = [
        (
            item.get("name"),
            item["prefix"],
            item.get("station_owner_name"), 
            item.get("city"),
            float(item["latitude"]),
            float(item["longitude"]),
            item["value"],
        )
        for item in data["json"]
        if item["latitude"] and item["longitude"] and item["value"]
    ]

    # Convert to DataFrame for easy display in Streamlit
    station_data_df = pd.DataFrame(
        stations,
        columns=['Nome', 'Prefixo', 'Proprietário', 'Município', 'Latitude', 'Longitude', 'Precipitação (mm)']
    )
    station_data_df = station_data_df.sort_values(by="Precipitação (mm)", ascending=False)

    
    # Filter stations based on excluded prefixes
    filtered_stations = [
        (name, prefix, owner, city, lat, lon, value)
        for name, prefix, owner, city, lat, lon, value in stations
        if prefix not in excluir_prefixos
    ]

    # Check for valid data after filtering
    if not filtered_stations:
        st.error("Erro: Não há dados válidos para exibição após a exclusão.")
        return

    # Display the data table
    st.write("Tabela Estações")
    st.dataframe(station_data_df,hide_index=True)  # Display data table in Streamlit

    # Create and display an interactive bar chart
    st.write("Gráfico Estações")
    fig = px.bar(
        station_data_df,
        x="Prefixo",
        y="Precipitação (mm)",
        labels={"Precipitação (mm)": "Precipitação (mm)", "Prefixo": "Prefixo Estação"},
        title="Precipitação por Estações",
    )
    st.plotly_chart(fig)



# Função para gerar o mapa de chuva
def gerar_mapa_chuva(url, titulo, excluir_prefixos):
    # Carregando a fronteira do estado de São Paulo e criando um shapefile temporário
    sp_border = gpd.read_file('./data/DIV_MUN_SP_2021a.shp').to_crs(epsg=4326)
    minx, miny, maxx, maxy = sp_border.total_bounds

    sp_border_shapefile = "results/sp_border.shp"
    sp_border.to_file(sp_border_shapefile)

    # Obtendo dados da API
    response = requests.get(url)
    data = response.json()

    # Extraindo coordenadas e valores
    stations = [
        (item["prefix"], float(item["latitude"]), float(item["longitude"]), item["value"])
        for item in data["json"]
        if item["latitude"] and item["longitude"] and item["value"]
    ]

    # Filtrando estações
    filtered_stations = [
        (lat, lon, value)
        for prefix, lat, lon, value in stations
        if prefix not in excluir_prefixos
    ]

    if not filtered_stations:
        st.error("Erro: Não há dados válidos para interpolação após a exclusão.")
        return

    # Separando latitudes, longitudes e valores
    lats, longs, values = zip(*filtered_stations)

    # Salvando os pontos em um shapefile temporário
    shapefile_path = "results/temp_points.shp"
    driver = ogr.GetDriverByName("ESRI Shapefile")
    dataSource = driver.CreateDataSource(shapefile_path)
    layer = dataSource.CreateLayer("layer", geom_type=ogr.wkbPoint)

    # Adicionando valores de precipitação
    layer.CreateField(ogr.FieldDefn("value", ogr.OFTReal))
    for lat, lon, value in zip(lats, longs, values):
        point = ogr.Geometry(ogr.wkbPoint)
        point.AddPoint(lon, lat)
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetGeometry(point)
        feature.SetField("value", value)
        layer.CreateFeature(feature)
        feature = None

    dataSource = None

    output_raster = f"results/raster_idw_{date_time_id}.tif"
    gdal.Grid(
        output_raster,
        shapefile_path,
        zfield="value",
        algorithm=f"invdist:power={power}:smoothing={smoothing}:radius={radius}",
        outputBounds=(minx, miny, maxx, maxy),
        width=1000, height=1000,
    )

    if not os.path.exists(output_raster):
        st.error(f"Erro: O raster intermediário {output_raster} não foi criado.")
        return

    # Definindo sistema de coordenadas EPSG:4326 no raster
    raster = gdal.Open(output_raster, gdal.GA_Update)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    raster.SetProjection(srs.ExportToWkt())
    raster = None

    cropped_raster = f"results/raster_idw_cropped_{date_time_id}.tif"
    gdal.Warp(
        cropped_raster,
        output_raster,
        cutlineDSName=sp_border_shapefile,
        cropToCutline=True,
        dstNodata=np.nan,
    )

    # Make upload to Geodados
    if upload_to_geonode:
        geodados.make_upload_to_geonode(f"raster_idw_cropped_{str(date_time_id)}",cropped_raster,{
        "title": "Chuva Acumulada 24h - "+str(ontem.strftime('%Y-%m-%d')),
            "abstract": "Chuva acumulada das últimas 24h do dia "+str(ontem.strftime('%Y-%m-%d')),
            "category": 19,
            "license": 4, 
        }, "styles/rainfall_daily_raster.sld")

    # Plot do resultado
    fig, ax = plt.subplots(figsize=(18, 12))

    # Carregar e plotar o raster recortado
    raster = gdal.Open(cropped_raster)
    if raster is None:
        st.error("Erro: O raster recortado não pôde ser aberto.")
        return

    raster_data = raster.ReadAsArray()

    cmap = ListedColormap([
        "#ffffff00", "#D5FFFF", "#00D5FF", "#0080AA", "#0000B3",
        "#80FF55", "#00CC7F", "#558000", "#005500", "#FFFF00",
        "#FFCC00", "#FF9900", "#D55500", "#FFBBFF", "#FF2B80", "#8000AA"
    ])
    

    norm = BoundaryNorm(selected_bounds, cmap.N)


    img = ax.imshow(raster_data, cmap=cmap, extent=(minx, maxx, miny, maxy), norm=norm)

    sp_border.plot(ax=ax, edgecolor='black', facecolor='none', linewidth=0.3)

    cbar = fig.colorbar(img, ax=ax, orientation="horizontal", label="Precipitação (mm)", shrink=0.75, pad=0.05, extend='max')
    cbar.set_ticks(selected_bounds)
    cbar.set_ticklabels([str(b) for b in selected_bounds])
    cbar.ax.tick_params(labelsize=12)

    logo_path = "./data/logo.png"
    if os.path.exists(logo_path):
        logo = Image.open(logo_path)
        imagebox = OffsetImage(logo, zoom=0.2)
        ab = AnnotationBbox(
            imagebox,
            (0.91, 0.91),
            xycoords='axes fraction',
            frameon=True,
            bboxprops=dict(facecolor="white", edgecolor='none')
        )
        ax.add_artist(ab)

    annotation_text = (
        "Interpolação dos pluviômetros a partir do método IDW.\n"
        "Elaborado pela equipe técnica da Sala de Situação São Paulo (SSSP)."
    )
    ax.annotate(
        annotation_text, xy=(0.02, 0.02), xycoords='axes fraction',
        fontsize=8, ha='left', va='bottom',
        bbox=dict(facecolor='white', alpha=0.7, edgecolor='white')
    )

    ax.set_title(f'{titulo}', fontsize=14)
    ax.grid(which='both', linestyle='-', linewidth=0.5, color='gray', alpha=0.6)
    ax.tick_params(axis='both', which='major', labelsize=8)

    st.pyplot(fig)


if st.button("Gerar Mapa"):
    gerar_mapa_chuva(url, titulo, excluir_prefixos)

if st.button("Gerar Tabela e Gráfico"):
    exibir_graficos_tabela(url, excluir_prefixos)
