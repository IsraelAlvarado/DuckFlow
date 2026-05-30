import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Configuración de reproducibilidad
np.random.seed(42)

# 1. PARÁMETROS DEL NEGOCIO
FECHA_INICIO = datetime(2024, 1, 1)
FECHA_FIN = datetime(2026, 5, 27)  # Datos hasta el día de hoy
PRODUCTOS = {
    'PROD001': {'nombre': 'Laptop Pro 15', 'categoria': 'Electrónica', 'costo_base': 800, 'precio_base': 1200},
    'PROD002': {'nombre': 'Monitor 4K 27', 'categoria': 'Electrónica', 'costo_base': 250, 'precio_base': 400},
    'PROD003': {'nombre': 'Teclado Mecánico RGB', 'categoria': 'Accesorios', 'costo_base': 45, 'precio_base': 90},
    'PROD004': {'nombre': 'Silla Ergonómica Premium', 'categoria': 'Muebles', 'costo_base': 150, 'precio_base': 300},
    'PROD005': {'nombre': 'Disco Duro Externo 2TB', 'categoria': 'Almacenamiento', 'costo_base': 40, 'precio_base': 75}
}
PROVEEDORES = ['LogiTech Global', 'Asia Freight Corp', 'EuroSupply Ltd']

# Generar rango de fechas completo
rango_fechas = pd.date_range(start=FECHA_INICIO, end=FECHA_FIN, freq='D')

print("🚀 Iniciando simulación de datos de Cadena de Suministro...")

# 2. GENERAR DIMENSIÓN PRODUCTOS (Dim_Producto)
def generar_productos():
    df_prod = pd.DataFrame([
        {
            'SKU': sku, 
            'Nombre_Producto': info['nombre'], 
            'Categoría': info['categoria'], 
            'Costo_Estándar': info['costo_base'], 
            'Precio_Lista': info['precio_base']
        } for sku, info in PRODUCTOS.items()
    ])
    df_prod.to_csv('data/raw/dim_productos.csv', index=False)
    print("✔ Dim_Productos generada con éxito.")

# 3. GENERAR HECHOS: VENTAS DIARIAS (Fact_Ventas)
def generar_ventas():
    ventas_list = []
    
    for fecha in rango_fechas:
        # Añadir estacionalidad básica (fines de semana se vende más)
        factor_dia = 1.3 if fecha.dayofweek >= 5 else 0.9
        # Estacionalidad de fin de año (Noviembre y Diciembre)
        factor_mes = 1.5 if fecha.month in [11, 12] else 1.0
        
        for sku, info in PRODUCTOS.items():
            # Decidir si hubo ventas de este producto hoy (probabilidad del 80%)
            if np.random.rand() > 0.2:
                # Cantidad base aleatoria multiplicada por factores estacionales
                cantidad = int(np.maximum(1, np.random.poisson(lam=10) * factor_dia * factor_mes))
                precio_unitario = round(info['precio_base'] * np.random.uniform(0.95, 1.05), 2)
                costo_unitario = info['costo_base']
                
                ventas_list.append({
                    'Fecha_Pedido': fecha.strftime('%Y-%m-%d'),
                    'SKU': sku,
                    'Cantidad_Vendida': cantidad,
                    'Precio_Unitario': precio_unitario,
                    'Costo_Unitario': costo_unitario,
                    'Ingreso_Total': round(cantidad * precio_unitario, 2)
                })
                
    df_ventas = pd.DataFrame(ventas_list)
    df_ventas.to_csv('data/raw/fact_ventas.csv', index=False)
    print(f"✔ Fact_Ventas generada con éxito ({len(df_ventas)} registros).")

# 4. GENERAR HECHOS: LOGÍSTICA Y ÓRDENES DE COMPRA (Fact_Inventario_Logistica)
def generar_logistica():
    logistica_list = []
    
    # Simulamos órdenes de compra enviadas a proveedores cada semana por producto
    fechas_ordenes = pd.date_range(start=FECHA_INICIO, end=FECHA_FIN, freq='W')
    
    for fecha in fechas_ordenes:
        for sku in PRODUCTOS.keys():
            proveedor = np.random.choice(PROVEEDORES)
            cantidad_pedida = int(np.random.randint(100, 300))
            
            # El proveedor puede tardar entre 3 y 12 días en entregar (Lead Time)
            lead_time_teorico = np.random.randint(4, 8)
            # Simular retrasos aleatorios en la cadena de suministro
            lead_time_real = lead_time_teorico + np.random.choice([0, 1, 2, 5], p=[0.6, 0.2, 0.1, 0.1])
            
            fecha_entrega = fecha + timedelta(days=int(lead_time_real))
            
            # Si la fecha de entrega supera la fecha fin del proyecto, se marca como 'En Tránsito'
            estado = 'Entregado' if fecha_entrega <= FECHA_FIN else 'En Tránsito'
            fecha_entrega_str = fecha_entrega.strftime('%Y-%m-%d') if estado == 'Entregado' else ''
            
            # Costo de envío afectado por variaciones logísticas
            costo_envio = round(cantidad_pedida * np.random.uniform(2, 5), 2)
            
            logistica_list.append({
                'ID_Orden_Compra': f"PO-{fecha.strftime('%Y%m%d')}-{sku}",
                'Fecha_Orden': fecha.strftime('%Y-%m-%d'),
                'Fecha_Entrega_Real': fecha_entrega_str,
                'SKU': sku,
                'Proveedor': proveedor,
                'Cantidad_Pedida': cantidad_pedida,
                'Lead_Time_Días': lead_time_real if estado == 'Entregado' else np.nan,
                'Costo_Envio_Total': costo_envio,
                'Estado_Envio': estado
            })
            
    df_logistica = pd.DataFrame(logistica_list)
    df_logistica.to_csv('data/raw/fact_logistica.csv', index=False)
    print(f"✔ Fact_Logistica generada con éxito ({len(df_logistica)} órdenes de compra).")

if __name__ == '__main__':
    generar_productos()
    generar_ventas()
    generar_logistica()
    print("🎉 Datos crudos aislados guardados exitosamente en data/raw/")