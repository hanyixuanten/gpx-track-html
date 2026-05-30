import gpxpy
import folium
import os
import math
import glob
from datetime import datetime, timedelta

# 定义可用的地图源
MAP_TILES = {
    "高德卫星图": "http://webst02.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
    "高德街道图": "http://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
}
# 地图源的属性信息
MAP_ATTRIBUTION = {
    "高德卫星图": '&copy; <a href="http://ditu.amap.com/">高德地图</a>',
    "高德街道图": '&copy; <a href="http://ditu.amap.com/">高德地图</a>'
}

def wgs84_to_gcj02(lng, lat):
    """
    WGS84转GCJ02(火星坐标系)
    将GPS的WGS84坐标转换为高德地图使用的GCJ02坐标
    """
    a = 6378245.0  # 长半轴
    ee = 0.00669342162296594323  # 扁率
    
    # 判断是否在国内
    if (lng < 72.004 or lng > 137.8347) or (lat < 0.8293 or lat > 55.8271):
        return lng, lat
    
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
    
    mglat = lat + dlat
    mglng = lng + dlng
    
    return mglng, mglat

def _transform_lat(lng, lat):
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * math.pi) + 320 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0
    return ret

def _transform_lng(lng, lat):
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * math.pi) + 40.0 * math.sin(lng / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * math.pi) + 300.0 * math.sin(lng / 30.0 * math.pi)) * 2.0 / 3.0
    return ret

def format_datetime(dt):
    """
    格式化日期时间，去掉时区信息
    """
    if dt:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return "未知"

def format_duration(seconds):
    """
    格式化持续时间
    """
    if seconds is None:
        return "未知"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}小时{minutes}分{secs}秒"
    elif minutes > 0:
        return f"{minutes}分{secs}秒"
    else:
        return f"{secs}秒"

def parse_gpx_file(gpx_file_path):
    """
    解析GPX文件，优化了速度平滑处理和运动时间计算（自动剔除暂停时间）
    """
    # 配置参数
    MAX_SPEED_THRESHOLD = 50.0  # 最高时速上限 (km/h)，超过此值可能是漂移
    PAUSE_THRESHOLD_SECONDS = 3 # 采样间隔超过3秒视为暂停
    SPEED_WINDOW_SIZE = 3        # 速度平滑窗口大小

    try:
        with open(gpx_file_path, 'r', encoding='utf-8') as gpx_file:
            gpx = gpxpy.parse(gpx_file)
        
        points = []
        total_distance = 0
        moving_time_seconds = 0  # 净运动时间
        start_time = None
        end_time = None
        
        # 临时存储速度用于平滑处理
        recent_speeds = []

        for track in gpx.tracks:
            for segment in track.segments:
                previous_point = None
                
                for i, point in enumerate(segment.points):
                    # 坐标转换
                    gcj_lng, gcj_lat = wgs84_to_gcj02(point.longitude, point.latitude)
                    
                    segment_distance = 0
                    raw_speed = 0
                    time_diff = 0
                    
                    if previous_point:
                        # 计算距离 (使用WGS84原始坐标计算距离更准确，再转换用于显示)
                        segment_distance = gpxpy.geo.haversine_distance(
                            previous_point['raw_lat'], previous_point['raw_lng'],
                            point.latitude, point.longitude
                        )
                        total_distance += segment_distance
                        
                        # 计算时间差
                        if point.time and previous_point['time']:
                            time_diff = (point.time - previous_point['time']).total_seconds()
                            
                            # --- 改进2：暂停检测逻辑 ---
                            # 如果时间间隔在阈值内，计入运动时间
                            if 0 < time_diff < PAUSE_THRESHOLD_SECONDS:
                                moving_time_seconds += time_diff
                            
                            # 计算原始速度
                            if time_diff > 0:
                                raw_speed = (segment_distance / time_diff) * 3.6 # km/h
                    
                    # --- 改进1：速度平滑处理 ---
                    # 剔除极端错误的数字
                    if raw_speed > MAX_SPEED_THRESHOLD:
                        raw_speed = recent_speeds[-1] if recent_speeds else 0
                    
                    recent_speeds.append(raw_speed)
                    if len(recent_speeds) > SPEED_WINDOW_SIZE:
                        recent_speeds.pop(0)
                    
                    # 取窗口平均值作为当前点的瞬时速度
                    smoothed_speed_kmh = sum(recent_speeds) / len(recent_speeds)
                    
                    # 记录时间
                    if i == 0 and point.time and not start_time:
                        start_time = point.time
                    
                    duration_from_start = (point.time - start_time).total_seconds() if start_time and point.time else 0

                    point_data = {
                        'latitude': gcj_lat,
                        'longitude': gcj_lng,
                        'raw_lat': point.latitude, # 保留原始坐标用于距离计算
                        'raw_lng': point.longitude,
                        'elevation': point.elevation,
                        'time': point.time,
                        'cumulative_distance': total_distance,
                        'instantaneous_speed': smoothed_speed_kmh / 3.6, # 转回 m/s 保持统一
                        'duration_from_start': duration_from_start,
                        'segment_distance': segment_distance
                    }
                    points.append(point_data)
                    previous_point = point_data

        if not points: return None
        
        end_time = points[-1]['time']
        
        # 计算总时长（包含暂停）
        total_duration_hours = (end_time - start_time).total_seconds() / 3600 if start_time and end_time else 0
        # 计算运动时长（剔除暂停）
        moving_duration_hours = moving_time_seconds / 3600

        # 其他统计逻辑 (海拔等) 保持不变...
        elevations = [p['elevation'] for p in points if p['elevation'] is not None]
        elevation_gain = 0
        if len(elevations) > 1:
            for i in range(1, len(elevations)):
                if elevations[i] > elevations[i-1]:
                    elevation_gain += elevations[i] - elevations[i-1]

        speeds_kmh = [p['instantaneous_speed'] * 3.6 for p in points]
        max_speed = max(speeds_kmh) if speeds_kmh else 0
        avg_speed = (total_distance / 1000) / moving_duration_hours if moving_duration_hours > 0 else 0

        return {
            'points': points,
            'total_distance': total_distance / 1000,
            'start_time': format_datetime(start_time),
            'end_time': format_datetime(end_time),
            'num_points': len(points),
            'min_elevation': min(elevations) if elevations else None,
            'max_elevation': max(elevations) if elevations else None,
            'avg_elevation': sum(elevations)/len(elevations) if elevations else None,
            'elevation_gain': elevation_gain,
            'duration_hours': moving_duration_hours, # 这里改为返回运动时间
            'total_elapsed_hours': total_duration_hours, # 保留一个总耗时
            'avg_speed': avg_speed,
            'max_speed': max_speed
        }
    except Exception as e:
        print(f"解析GPX文件时出错: {e}")
        return None

def create_map_with_track(gpx_data, output_file='gpx_track_map.html'):
    """
    使用folium创建带有轨迹的地图，默认提供多个地图源选项
    添加鼠标悬停显示路程、速度和时间功能
    轨迹始终显示，没有选择框控制
    """
    if not gpx_data or not gpx_data['points']:
        print("没有轨迹数据可显示")
        return
    
    points = gpx_data['points']
    
    # 计算地图中心点
    center_lat = sum(p['latitude'] for p in points) / len(points)
    center_lon = sum(p['longitude'] for p in points) / len(points)
    
    # 创建地图 - 使用高德街道图作为默认地图
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles=None  # 不设置默认瓦片
    )
    
    # 添加所有地图源作为可选图层
    for tile_name, tile_url in MAP_TILES.items():
        folium.TileLayer(
            tiles=tile_url,
            attr=MAP_ATTRIBUTION[tile_name],
            name=tile_name
        ).add_to(m)
    
    # 创建轨迹线的坐标列表和对应的工具提示数据
    track_coordinates = []
    tooltip_data = []
    
    for point in points:
        track_coordinates.append((point['latitude'], point['longitude']))
        
        # 准备工具提示信息
        distance_km = point['cumulative_distance'] / 1000
        speed_kmh = point['instantaneous_speed'] * 3.6  # 转换为km/h
        
        tooltip = f"""
        <div style="font-size: 12px; font-family: Arial, sans-serif;">
            <b>位置信息</b><br>
            路程: {distance_km:.2f} km<br>
            速度: {speed_kmh:.1f} km/h<br>
            时间: {format_datetime(point['time'])}<br>
            持续时间: {format_duration(point['duration_from_start'])}
        </div>
        """
        tooltip_data.append(tooltip)
    
    # 创建轨迹线 - 直接添加到地图，不使用FeatureGroup
    track_line = folium.PolyLine(
        track_coordinates,
        color='red',
        weight=5,
        opacity=0.8,
        popup='GPS轨迹'
    )
    track_line.add_to(m)
    
    # 添加透明的多边形覆盖物用于捕获鼠标事件
    for i in range(len(track_coordinates) - 1):
        # 创建两个相邻点之间的小线段
        segment_coords = [track_coordinates[i], track_coordinates[i + 1]]
        
        # 使用半透明的多边形来捕获悬停事件
        hover_polygon = folium.PolyLine(
            segment_coords,
            color='transparent',
            weight=15,  # 较宽的透明线以便于悬停
            opacity=0.01,  # 几乎完全透明
            tooltip=folium.Tooltip(
                tooltip_data[i + 1],  # 显示后一个点的信息
                sticky=False,
                permanent=False
            )
        )
        hover_polygon.add_to(m)
    
    # 添加起点标记
    start_point = points[0]
    folium.Marker(
        [start_point['latitude'], start_point['longitude']],
        popup=f"起点\n时间: {format_datetime(start_point['time'])}",
        tooltip="起点",
        icon=folium.Icon(color='green', icon='play', prefix='fa')
    ).add_to(m)
    
    # 添加终点标记
    end_point = points[-1]
    folium.Marker(
        [end_point['latitude'], end_point['longitude']],
        popup=f"终点\n时间: {format_datetime(end_point['time'])}",
        tooltip="终点",
        icon=folium.Icon(color='red', icon='stop', prefix='fa')
    ).add_to(m)
    
    # 在轨迹上添加关键点标记（每25%的距离添加一个）
    num_key_points = 4
    for i in range(1, num_key_points):
        target_distance = (gpx_data['total_distance'] * 1000) * (i / num_key_points)
        
        # 找到最接近目标距离的点
        closest_point = min(points, key=lambda x: abs(x['cumulative_distance'] - target_distance))
        
        folium.CircleMarker(
            [closest_point['latitude'], closest_point['longitude']],
            radius=4,
            popup=f"路程: {closest_point['cumulative_distance']/1000:.2f} km",
            tooltip=f"{i*25}% 路程点",
            color='blue',
            fill=True,
            fillColor='blue'
        ).add_to(m)
    
    # 添加信息框 - 缩小尺寸并添加最高速度
    info_html = f"""
    <div style="position: fixed; 
                top: 10px; left: 10px; width: 280px; height: auto; 
                background-color: white; border:2px solid grey; z-index:9999; 
                padding: 8px; font-size:12px; border-radius: 5px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.3);">
        <b style="font-size:13px;">轨迹信息</b><br>
        总距离: {gpx_data['total_distance']:.2f} km<br>
        轨迹点数: {gpx_data['num_points']}<br>
        开始时间: {gpx_data['start_time']}<br>
        结束时间: {gpx_data['end_time']}<br>
    """
    
    # 添加海拔信息（如果存在）
    if gpx_data['min_elevation'] is not None:
        info_html += f"最低海拔: {gpx_data['min_elevation']:.1f} m<br>"
        info_html += f"最高海拔: {gpx_data['max_elevation']:.1f} m<br>"
        info_html += f"平均海拔: {gpx_data['avg_elevation']:.1f} m<br>"
        info_html += f"累计爬升: {gpx_data['elevation_gain']:.0f} m<br>"
    
    # 添加时间和速度信息
    if gpx_data['duration_hours'] > 0:
        hours = int(gpx_data['duration_hours'])
        minutes = int((gpx_data['duration_hours'] - hours) * 60)
        info_html += f"持续时间: {hours}时{minutes}分<br>"
        info_html += f"平均速度: {gpx_data['avg_speed']:.1f} km/h<br>"
        info_html += f"<b>最高速度: {gpx_data['max_speed']:.1f} km/h</b><br>"
    
    info_html += "<br><b>使用提示:</b> 鼠标悬停轨迹查看详情"
    info_html += "</div>"
    m.get_root().html.add_child(folium.Element(info_html))
    
    # 添加图层控制（只控制地图源，不控制轨迹）
    folium.LayerControl().add_to(m)
    
    # 保存地图
    m.save(output_file)
    return m

def batch_process_gpx_files(folder_path):
    """
    批量处理文件夹中的所有GPX文件
    """
    gpx_files = glob.glob(os.path.join(folder_path, "*.gpx"))
    
    if not gpx_files:
        print("在指定文件夹中未找到GPX文件")
        return
    
    processed_count = 0
    
    for gpx_file in gpx_files:
        print(f"正在处理: {os.path.basename(gpx_file)}")
        gpx_data = parse_gpx_file(gpx_file)
        
        if gpx_data:
            output_filename = os.path.splitext(gpx_file)[0] + '_map.html'
            create_map_with_track(gpx_data, output_filename)
            processed_count += 1
            print(f"  已生成: {os.path.basename(output_filename)}")
    
    return processed_count

if __name__ == "__main__":
    print("GPX轨迹可视化工具")
    print("正在处理当前文件夹中的GPX文件...")
    
    # 获取当前程序所在文件夹路径
    current_folder = os.path.dirname(os.path.abspath(__file__))
    
    # 批量处理当前文件夹中的所有GPX文件
    processed_count = batch_process_gpx_files(current_folder)
    
    print(f"处理完成！共生成 {processed_count} 个地图文件")
    print("请在浏览器中打开生成的HTML文件查看轨迹地图")
    print("提示：您可以在右上角切换不同的地图图层")
    print("新功能：鼠标悬停在轨迹线上可以查看实时路程、速度和时间信息")