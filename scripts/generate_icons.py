import os
import subprocess
from pathlib import Path

def main():
    root = Path(__file__).resolve().parent.parent
    svg_path = root / "app" / "static" / "magic-icon.svg"
    
    if not svg_path.exists():
        print(f"Error: {svg_path} not found.")
        return
        
    sizes = [128, 256, 1024]
    png_paths = []
    
    print("Generating PNGs from SVG...")
    for size in sizes:
        out_path = root / "app" / "static" / f"magic-icon-{size}.png"
        subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), str(svg_path), "-o", str(out_path)], check=False)
        if out_path.exists():
            png_paths.append(out_path)
            print(f"Generated {out_path.name}")
            
    # Create ICNS if we have the 1024 PNG and we are on macOS
    png_1024 = root / "app" / "static" / "magic-icon-1024.png"
    icns_path = root / "Magic.app" / "Contents" / "Resources" / "Magic.icns"
    
    if png_1024.exists() and os.name == 'posix':
        print("Creating iconset and ICNS...")
        iconset_dir = root / "Magic.iconset"
        iconset_dir.mkdir(exist_ok=True)
        subprocess.run(["sips", "-z", "1024", "1024", str(png_1024), "--out", str(iconset_dir / "icon_512x512@2x.png")])
        subprocess.run(["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)])
        subprocess.run(["rm", "-rf", str(iconset_dir)])
        print(f"Generated {icns_path}")

if __name__ == "__main__":
    main()