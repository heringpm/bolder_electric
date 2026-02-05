# PIL/Pillow Installation Troubleshooting

## Issue: ModuleNotFoundError despite Pillow being installed

**Symptoms:**
- `pip install Pillow==10.0.0` shows "Requirement already satisfied"
- `pip list` shows Pillow==10.0.0 is installed
- Python still shows `ModuleNotFoundError: No module named 'PIL'`

**Root Cause:**
- Pillow is installed as `Pillow` but Python still looks for `PIL` module
- This is a common issue with Pillow/PIL naming

**Solutions:**

#### Option 1: Force PIL Import (Recommended)
Add this to your app.py:
```python
# Force PIL module mapping before any other imports
import sys
sys.modules['PIL'] = __import__('PIL.Image')
from PIL import Image
```

#### Option 2: Use Only Pillow Import
Replace all PIL imports with Pillow:
```python
# Replace: from PIL import Image
# With: from PIL import Image  # This works with modern Pillow
```

#### Option 3: Check Python Path
```bash
python3 -c "import sys; print(sys.path)"
python3 -c "import PIL; print(PIL.__file__)"
```

#### Option 4: Virtual Environment Check
```bash
# Check if using correct Python
which python3
python3 -m pip list | grep Pillow

# Check if in virtual environment
echo $VIRTUAL_ENV
pip list | grep Pillow
```

### AWS Deployment Fix:
```bash
# Force PIL module mapping before starting app
export PYTHONPATH="/home/gunicorn/.local/lib/python3.9/site-packages:$PYTHONPATH"
python3 -c "import sys; sys.modules['PIL'] = __import__('PIL.Image'); from PIL import Image; print('PIL import successful')"

# Then start the app
sudo systemctl restart bolder-electric
```

### Quick Fix Commands:

```bash
# Test PIL import
python3 -c "from PIL import Image; print('PIL works!')"

# Force PIL mapping and restart
export PYTHONPATH="/home/gunicorn/.local/lib/python3.9/site-packages:$PYTHONPATH"
sudo systemctl restart bolder-electric

# Alternative: Use only Pillow import
# Edit app.py to use: from PIL import Image
```
