#!/bin/bash
sudo su
yum install git -y
yum install nodejs -y
yum install pip -y
npm install pm2 -g -y
yum install postgresql15.x86_64 postgresql15-server -y
yum install postgresql-devel python3-devel
git clone 
pip install -r requirements.txt