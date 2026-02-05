#!/usr/bin/env python3

# Test script to verify PIL import
try:
    from PIL import Image
    print("✅ PIL import successful!")
    print(f"PIL version: {Image.__version__}")
except ImportError as e:
    print(f"❌ PIL import failed: {e}")
    print("Make sure Pillow is installed: pip install Pillow==10.0.0")
