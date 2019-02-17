if [[ $(python lambdanaut/__init__.py | grep -i "DEBUG") ]]; then
    echo "Debug mode is turned on. Not compiling."
else
    filename=$(python lambdanaut/__init__.py | grep -i "lambdanaut")
    filename+=".zip"

    echo "Compiling project into .zip"

    # Zip up all python, markdown, and library files
    # Ignore any other files
    zip -R $filename '*.py' '*.md' 'lib/*'
fi
