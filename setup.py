from setuptools import setup, find_packages

setup(
    name='sync',
    version='0.1',
    description='Synchronize changes between gecko and web-platform-tests',
    url='https://web-platform-tests.org',
    author='Mozilla',
    author_email='mozilla-tools@lists.mozilla.org',
    license='MPL 2.0',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 2.7',
    ],
    packages=find_packages(),
    entry_points={
       "console_scripts": [
           "wptsync = sync.command:main"
       ]
    },
    install_requires=[
    ],
)
