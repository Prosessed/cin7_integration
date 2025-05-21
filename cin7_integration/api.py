import requests
import json





def create_sales_order_on_cin7(sales_order):
    # Define the API endpoint and headers
    api_url = "https://inventory.dearsystems.com/ExternalApi/Sale"
