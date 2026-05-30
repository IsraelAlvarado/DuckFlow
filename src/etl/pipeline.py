import os
import yaml
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

class SupplyChainETL:
    def __init__(self):
        load_dotenv()
        self.source_dir = Path(os.getenv("DATASET_SOURCE_DIR"))
        self.output_dir = Path(os.getenv("DATASET_OUTPUT_DIR"))
        self.config = self._load_config()

    def _load_config(self):
        with open("config.yaml", "r") as f:
            return yaml.safe_load(f)

    def extract_and_transform(self):
        files = self.config["pipeline"]["target_files"]
        
        # Carga de fuentes externas
        df_orders = pd.read_csv(self.source_dir / files["orders"])
        df_items = pd.read_csv(self.source_dir / files["items"])
        df_products = pd.read_csv(self.source_dir / files["products"])

        # Conversión de tipos y limpieza de fechas
        date_columns = [
            "order_purchase_timestamp", 
            "order_delivered_carrier_date", 
            "order_delivered_customer_date", 
            "order_estimated_delivery_date"
        ]
        for col in date_columns:
            df_orders[col] = pd.to_datetime(df_orders[col])

        if self.config["pipeline"]["cleaning"]["drop_missing_dates"]:
            df_orders = df_orders.dropna(subset=["order_delivered_customer_date"])

        # Transformación avanzada: Métricas de Supply Chain
        df_orders["lead_time_days"] = (df_orders["order_delivered_customer_date"] - df_orders["order_purchase_timestamp"]).dt.days
        df_orders["delivery_delay_days"] = (df_orders["order_delivered_customer_date"] - df_orders["order_estimated_delivery_date"]).dt.days

        # Construcción del modelo relacional procesado
        # Fact Table: Ventas y Logística combinadas
        fact_supply_chain = df_items.merge(df_orders, on="order_id", how="inner")
        
        # Dimension Table: Productos
        fill_val = self.config["pipeline"]["cleaning"]["fill_missing_categories"]
        df_products["product_category_name"] = df_products["product_category_name"].fillna(fill_val)

        # Almacenamiento en la capa procesada aislada
        self.output_dir.mkdir(parents=True, exist_ok=True)
        fact_supply_chain.to_csv(self.output_dir / "fact_supply_chain.csv", index=False)
        df_products.to_csv(self.output_dir / "dim_products.csv", index=False)

if __name__ == "__main__":
    etl = SupplyChainETL()
    etl.extract_and_transform()