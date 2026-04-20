import pdfplumber
import os

# Buscar el archivo PDF en el directorio actual
pdf_path = "CV Eloisa Sanhueza.pdf"

# Si no existe, buscar en el directorio de uploads
if not os.path.exists(pdf_path):
    pdf_path = "uploads/CV Eloisa Sanhueza.pdf"
    
if not os.path.exists(pdf_path):
    # Listar archivos PDF en el directorio actual
    print("Archivos PDF encontrados en el directorio actual:")
    for file in os.listdir('.'):
        if file.endswith('.pdf'):
            print(f"  - {file}")
    print(f"\nNo se encontró el archivo. Por favor, especifica la ruta correcta.")
    exit(1)

print(f"Analizando: {pdf_path}\n")

with pdfplumber.open(pdf_path) as pdf:
    for page_num, page in enumerate(pdf.pages, 1):
        text = page.extract_text()
        lines = text.split('\n')
        
        print(f"\n{'='*60}")
        print(f"PÁGINA {page_num}")
        print(f"{'='*60}")
        
        for i, line in enumerate(lines):
            if 'Movimientos' in line or 'SALDOS' in line:
                print(f"Línea {i}: {repr(line)}")
        
        print("\n--- Líneas después de Movimientos ---")
        in_movements = False
        for line in lines:
            if 'Movimientos' in line:
                in_movements = True
                continue
            if in_movements and ('Saldos' in line or 'SALDOS' in line):
                break
            if in_movements and line.strip():
                print(repr(line))
        
        # También mostrar coordenadas de palabras en la primera página
        if page_num == 1:
            print("\n--- Coordenadas de palabras (primeras 30 palabras) ---")
            words = page.extract_words()
            for i, word in enumerate(words[:30]):
                print(f"{i}: text='{word['text']}', x0={word['x0']:.1f}, x1={word['x1']:.1f}, top={word['top']:.1f}")