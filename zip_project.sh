# Disallows compilation if debug mode is true
debug_mode=$(python lambdanaut/__init__.py | grep -i "DEBUG")

if [[ "$debug_mode" == "DEBUG MODE: False" ]]; then
    filename=$(python lambdanaut/__init__.py | grep -i "lambdanaut")
    filename+=".zip"

    echo "Compiling project into .zip"

    # Zip up all python, markdown, and library files
    # Ignore any other files
    zip -R $filename '*.py' '*.md' 'lib/*' 'ladderbots.json'
else
    echo "Debug mode is turned on. Not compiling."
fi
