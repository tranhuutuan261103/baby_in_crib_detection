from flask import Flask, request, jsonify

app = Flask(__name__)

from controllers.baby_in_crib_detection_controller import bicd_bp

app.register_blueprint(bicd_bp)

if __name__ == "__main__":
    app.run(host='0.0.0.0',port=5123,debug=True)