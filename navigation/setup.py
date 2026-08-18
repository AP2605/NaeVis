"""
Setup configuration for Navis Navigation & Localization Package (P3).
"""

from setuptools import setup, find_packages

setup(
    name="navis-navigation",
    version="1.0.0",
    description="Autonomous GPS-Denied Navigation & Localization Engine for SIH Hackathon (P3)",
    author="Team Navis (P3)",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "numpy>=1.22.0",
        "scipy>=1.8.0",
        "opencv-python>=4.5.0",
        "matplotlib>=3.5.0",
        "pyyaml>=6.0",
        "pandas>=1.3.0"
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Topic :: Scientific/Engineering :: Robotics",
        "Topic :: Scientific/Engineering :: Image Recognition"
    ]
)
