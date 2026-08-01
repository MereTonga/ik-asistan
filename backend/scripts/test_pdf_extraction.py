import os
import pdfplumber

PDF_PATH = os.path.join(os.path.dirname(__file__), "test_files/ornek.pdf")  # kendi dosya adınla değiştir

def main():
    with pdfplumber.open(PDF_PATH) as pdf:
        print(f"Toplam sayfa: {len(pdf.pages)}\n")
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            print(f"--- SAYFA {i+1} ---")
            print(text)
            print()

            tables = page.extract_tables()
            if tables:
                print(f"[Bu sayfada {len(tables)} tablo bulundu]")
                for t in tables:
                    print(t)

if __name__ == "__main__":
    main()
