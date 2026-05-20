import google.generativeai as genai
import os

# Asegúrate de tener configurada tu variable de entorno GEMINI_API_KEY
genai.configure(api_key="AIzaSyAGImxwYSuGNcptAZT8LCl_xkAf20CO-aY")

try:
    # Usamos el alias "-latest"
    modelo = genai.GenerativeModel("models/gemini-2.5-flash-lite")
    
    print("Conectando con Gemini 1.5 Flash 8B...")
    respuesta = modelo.generate_content("Responde solo con la palabra: 'Conectado'")
    
    print(f"Éxito: {respuesta.text}")

except Exception as e:
    print(f"Hubo un error: {e}")