"""pytest가 프로젝트 루트 모듈(config, strategy 등)을 import할 수 있게 경로 추가."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
