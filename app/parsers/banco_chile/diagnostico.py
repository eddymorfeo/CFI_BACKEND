import pdfplumber

with pdfplumber.open("CC Andrea Sanhueza OK.pdf") as pdf:
    for page_num in range(min(3, len(pdf.pages))):  # Primeras 3 páginas
        page = pdf.pages[page_num]
        text = page.extract_text()
        
        print(f"\n{'='*80}")
        print(f"PÁGINA {page_num + 1}")
        print(f"{'='*80}\n")
        print(text)
        
        # También extraer tablas si existen
        tables = page.extract_tables()
        if tables:
            print(f"\n--- TABLAS ENCONTRADAS (PÁGINA {page_num + 1}) ---")
            for table_idx, table in enumerate(tables):
                print(f"\nTabla {table_idx + 1}:")
                for row_idx, row in enumerate(table[:10]):  # primeras 10 filas
                    print(f"  Fila {row_idx}: {row}")