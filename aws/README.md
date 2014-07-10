# Setup a cluster on AWS

## Generate the template

The cloudformation template is a JSON file that describes the parameters and the resources to provision. Since it's JSON it's not easy to debug or comment. In order to deal with that, we use `troposphere` which is a simple python library that offer methods to generate the JSON template. So, to generate the template, juste type the following commands :

    pip install -r requirements.txt
    python cloudformation-template.py > nuxeo.io-template.json


It generates a `nuxeo.io-template.json` file that you can use for the next step.

*Warning:* the current template contains a dedicated etcd cluster discovery URL; so you can't use it several times.


## Run the template

Go to your AWS console and select the [CloudFormation service](https://console.aws.amazon.com/cloudformation/home).

  * Click on **Create Stack**
  * Give a name to your stack, for instance **ioTest**
  * Select **Upload template file** and choose the previously generated file
  * Click on **Next Step**

Go to https://discovery.etcd.io/a8fa665472cd41caa07b656ba30ba343 and copy the content of the page : this is the discovery URL for the `etcd` service.

On the next screen, you have to fill in the form with the parameter you want. Click **Next Step**, add some additional tags or specify an email address to get notified when the stack is provision. Click **Next Step** and after reviewing your parameters, click on **Create**.

After a while, your cluster should be up and runnning.

## Setup DB, S3, manager and OAuth

    fleetctl destroy postgres-service.service
    fleetctl destroy vblob-service.service

    etcdctl set /services/postgres-service/1/location '{"host":"iotest.c8kjrn5wzug3.eu-west-1.rds.amazonaws.com","port":5432}'
    etcdctl set /services/s3/1/location '{"host":"s3-eu-west-1.amazonaws.com","port":80}'

    etcdctl set /config/s3/bucket iotest
    etcdctl set /config/s3/awsid {AWSID}
    etcdctl set /config/s3/awssecret {AWSSECRET}
    etcdctl set /config/s3/region eu-west-1

    etcdctl set /services/manager/config/domain manager.trial.nuxeo.io
    etcdctl set /services/manager/config/defaultDomainSuffix trial.nuxeo.io

    etcdctl set /config/manager/oauth '{"key":"MY_KEY","secret":"MY_SECRET"}'

## Setup Route53

In order to be able to reach the cluster:

  * go to EC2 services page
  * Click on **Load balancers** in the left column
  * Copy the DNS name of the Load balancer created by the template (its name should start with the cluster's name)
  * Got to Route 53 service page
  * Add a CNAME from a catchall recordset (*.mycluster.com) to the DNS name of the loadbalancer.
