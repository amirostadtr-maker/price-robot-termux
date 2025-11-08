#!/system/bin/sh
set -e
echo "✅ Starting Termux One-Shot Installer ..."
pkg update -y && pkg upgrade -y
pkg install -y python git clang openssl redis postgresql python-numpy python-pandas curl
pip install --upgrade pip
pip install flask pandas aiohttp beautifulsoup4 lxml fake-useragent langdetect scikit-learn openpyxl tenacity
mkdir -p ~/pricebot && cd ~/pricebot
curl -o robot.py https://raw.githubusercontent.com/YOUR_USERNAME/price-robot-termux/main/robot.py || \
cat > robot.py << 'EOF'
(کد کامل robot.py را اینجا بگذار)
EOF
chmod +x robot.py
echo "✅ Ready! Run: cd ~/pricebot && python robot.py"
python robot.py
