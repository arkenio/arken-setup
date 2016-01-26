#!/usr/bin/python


from troposphere import Output, GetAtt, Base64, FindInMap, Parameter, Ref, Template, GetAZs, Join, Tags, Select, If
import troposphere.ec2 as ec2
import troposphere.autoscaling as autoscaling
import troposphere.elasticloadbalancing as elb
import troposphere.rds as rds
from troposphere.iam import AccessKey, Group, LoginProfile, PolicyType
from troposphere.iam import User, UserToGroupAddition
from troposphere.s3 import Bucket, Private
from troposphere.route53 import RecordSetType
import re
import urllib2

t = Template()

"""
Profile map that defines various parameters that may
affect performance and price.
"""
t.add_mapping('Profile', {
    "prod" : {
        "InstanceType": "m3.2xlarge",
        "ClusterSize": "4",
        "MultiAZ" : True,
        "DBAllocatedStorage" : "50",
        "DBInstanceType" : "db.m3.2xlarge",
        "DBBackupRetentionPeriod": 7

        },
    "stress" : {
        "InstanceType": "m3.xlarge",
        "ClusterSize": "4",
        "MultiAZ" : False,
        "DBAllocatedStorage" : "10",
        "DBInstanceType" : "db.m3.xlarge",
        "DBBackupRetentionPeriod": 0
    },
    "preprod" : {
        "InstanceType": "m3.large",
        "ClusterSize": "3",
        "MultiAZ" : False,
        "DBAllocatedStorage" : "10",
        "DBInstanceType" : "db.m3.large",
        "DBBackupRetentionPeriod": 1
        },
    "test" : {
        "InstanceType": "m3.large",
        "ClusterSize": "3",
        "MultiAZ" : False,
        "DBAllocatedStorage" : "5",
        "DBInstanceType" : "db.m3.large",
        "DBBackupRetentionPeriod": 0
        }
    })





"""
CoreOS AMIs
"""
t.add_mapping('RegionMap', {
    "ap-northeast-1" : {
        "AMI" : "ami-e2465fe3"
        },

    "sa-east-1" : {
        "AMI" : "ami-7f863a62"
        },

    "ap-southeast-2" : {
        "AMI" : "ami-db7d09e1"
        },

    "ap-southeast-1" : {
        "AMI" : "ami-3e8da66c"
        },

    "us-east-1" : {
        "AMI" : "ami-3615525e"
        },

    "us-west-2" : {
        "AMI" : "ami-51134b61"
        },

    "us-west-1" : {
        "AMI" : "ami-bebfa6fb"
        },

    "eu-west-1" : {
        "AMI" : "ami-7bf27e0c"
        }
    })




"""
Declaration of parameters used in the cloud formation template
"""
profile_param = t.add_parameter(Parameter(
  "ClusterProfile",
  Description="Cluster profile (in prod, preprod, test or stress)",
  AllowedValues=["prod", "preprod", "test","stress"],
  Default="test",
  Type="String"
))

dbPassword_param = t.add_parameter(Parameter(
  "DBPassword",
  Description="Master user password for database",
  Type="String",
  NoEcho=True
))

discovery_param = t.add_parameter(Parameter(
  "DiscoveryParam",
  Description="An unique etcd cluster discovery URL. Grab a new token from https://discovery.etcd.io/new",
  Type="String"
))


keyPair_param = t.add_parameter(Parameter(
  "KeyPair",
  Description="The name of an EC2 Key Pair to allow SSH access to the instance.",
  Type="String"
))

"""domain_param = t.add_parameter(Parameter(
  "DomainName",
  Description="The name of the domain that the cluster will handle (eg: test.io.nuxeo.com)",
  Type="String",
  MinLength=5,
))"""

hostedzone = t.add_parameter(Parameter(
    "HostedZone",
    Description="The DNS name of an existing Amazon Route 53 hosted zone where the wildcard domain will be declared",
    Type="String",
))

sslCertificateId_param = t.add_parameter(Parameter(
    "SSLCertificateId",
    Description="The id of the wildcard SSL certificate to use for the HTTPS load balancer",
    Type="String",
    Default="wildcard.test.io.nuxeo.com",
))



"""
Network configuration

We create  :
 * a VPC
 * 2 subnets
 * an Internet Gateway
 * 2 security groups
 * 1 load balancer
 * 1 DB subnet group (if MultiAZ)
 * 1 DB instance
 * 1 S3 bucket
 * 1 DNS wildcard record
"""



vpc = t.add_resource(ec2.VPC(
  "ioVPC",
  CidrBlock= "172.32.0.0/16",
  EnableDnsSupport= True,
  EnableDnsHostnames= True,
  Tags=Tags(
        IoCluster=Ref("AWS::StackName"),
        Name=Join("-",[Ref("AWS::StackName"), "vpc" ])
    ),
))

privateSubnetA = t.add_resource(ec2.Subnet(
  "ioPrivateSubneta",
  AvailabilityZone=Select(0,GetAZs("")),
  CidrBlock= "172.32.16.0/20",
  VpcId= Ref(vpc),
  Tags=Tags(
        IoCluster=Ref("AWS::StackName"),
        Name=Join("-",[Ref("AWS::StackName"), "privateSubnet-a" ])
    ),
))

privateSubnetB = t.add_resource(ec2.Subnet(
  "ioPrivateSubnetb",
  AvailabilityZone=Select(1,GetAZs("")),
  CidrBlock= "172.32.32.0/20",
  VpcId= Ref(vpc),
  Tags=Tags(
        IoCluster=Ref("AWS::StackName"),
        Name=Join("-",[Ref("AWS::StackName"), "privateSubnet-b" ])
    ),
))

privateSubnetC = t.add_resource(ec2.Subnet(
  "ioPrivateSubnetc",
  AvailabilityZone=Select(2,GetAZs("")),
  CidrBlock= "172.32.48.0/20",
  VpcId= Ref(vpc),
  Tags=Tags(
        IoCluster=Ref("AWS::StackName"),
        Name=Join("-",[Ref("AWS::StackName"), "privateSubnet-c" ])
    ),
))


publicSubnet = t.add_resource(ec2.Subnet(
  "ioPublicSubnet",
  AvailabilityZone=Select(0,GetAZs("")),
  CidrBlock= "172.32.0.0/20",
  VpcId= Ref(vpc),
  Tags=Tags(
        IoCluster=Ref("AWS::StackName"),
        Name=Join("-",[Ref("AWS::StackName"), "publicSubnet" ])
    )
))

ig = t.add_resource(ec2.InternetGateway(
  "ioGateway",
  Tags=Tags(
        IoCluster=Ref("AWS::StackName"),
        Name=Join("-",[Ref("AWS::StackName"), "privateSubnet-a" ])
    )
))

igAttachment = t.add_resource(ec2.VPCGatewayAttachment(
  "IgAttachment",
  InternetGatewayId=Ref(ig),
  VpcId=Ref(vpc)

))


ioRouteTable = t.add_resource(ec2.RouteTable(
  "ioRouteTable",
  VpcId=Ref(vpc),
  Tags=Tags(
        IoCluster=Ref("AWS::StackName"),
        Name=Join("-",[Ref("AWS::StackName"), "routeTable" ])
    )

))

publicRoute = t.add_resource(ec2.Route(
  "ioRoute",
  RouteTableId=Ref(ioRouteTable),
  DestinationCidrBlock="0.0.0.0/0",
  GatewayId=Ref(ig)
))

publicSubnetRoutAssociation = t.add_resource(ec2.SubnetRouteTableAssociation(
  "publicSubnetRouteAssociation",
  SubnetId=Ref(publicSubnet),
  RouteTableId=Ref(ioRouteTable)
))

privateSubnetRoutAssociation = t.add_resource(ec2.SubnetRouteTableAssociation(
  "privateASubnetRouteAssociation",
  SubnetId=Ref(privateSubnetA),
  RouteTableId=Ref(ioRouteTable)
))

privateSubnetRoutAssociation = t.add_resource(ec2.SubnetRouteTableAssociation(
  "privateBSubnetRouteAssociation",
  SubnetId=Ref(privateSubnetB),
  RouteTableId=Ref(ioRouteTable)
))


privateSubnetRoutAssociation = t.add_resource(ec2.SubnetRouteTableAssociation(
  "privateCSubnetRouteAssociation",
  SubnetId=Ref(privateSubnetC),
  RouteTableId=Ref(ioRouteTable)
))


"""
This is the SG reachable via HTTP. The front LB will belong to
that SG.
"""
publicFacingSG = t.add_resource(ec2.SecurityGroup(
    "publicSG",
    VpcId=Ref(vpc),
    GroupDescription="Enable HTTP, HTTPs access from everywhere ",
    SecurityGroupIngress=[
        ec2.SecurityGroupRule(
            IpProtocol="tcp",
            FromPort="80",
            ToPort="80",
            CidrIp="0.0.0.0/0",
        ),
        ec2.SecurityGroupRule(
            IpProtocol="tcp",
            FromPort="443",
            ToPort="443",
            CidrIp="0.0.0.0/0",
        ),
    ],
    Tags=Tags(
        IoCluster=Ref("AWS::StackName"),
        Name=Join("-",[Ref("AWS::StackName"), "public-SG" ])
    )
))



"""
SecurityGroup where all host of the cluster add_resource
It's reachable via SSH for configured CIDR in parameters.
All communication inside the SG are allowed.
"""
ioClusterSG = t.add_resource(ec2.SecurityGroup(
    "IOClusterSG",
    VpcId=Ref(vpc),
    GroupDescription="Enable SSH access via port 22",
    SecurityGroupIngress=[
        ec2.SecurityGroupRule(
            IpProtocol="tcp",
            FromPort="22",
            ToPort="22",
            CidrIp="0.0.0.0/0",
        ),
    ],
    Tags=Tags(
        IoCluster=Ref("AWS::StackName"),
        Name=Join("-",[Ref("AWS::StackName"), "private-SG" ])
    )
))

ioClusterSGInternalIngressALL = t.add_resource(ec2.SecurityGroupIngress(
  "IoClusterSGInternalIngressALL",
  GroupId= Ref(ioClusterSG),
  IpProtocol="tcp",
  FromPort="0",
  ToPort="65535",
  SourceSecurityGroupId= Ref(ioClusterSG)
))

ioClusterSGInternalIngressALLICMP = t.add_resource(ec2.SecurityGroupIngress(
  "IoClusterSGInternalIngressALLICMP",
  GroupId= Ref(ioClusterSG),
  IpProtocol="icmp",
  FromPort="-1",
  ToPort="-1",
  SourceSecurityGroupId= Ref(ioClusterSG)
))


ioClusterSGInternalIngress7777 = t.add_resource(ec2.SecurityGroupIngress(
  "IoClusterSGInternalIngress7777",
  GroupId= Ref(ioClusterSG),
  IpProtocol="tcp",
  FromPort="7777",
  ToPort="7777",
  SourceSecurityGroupId= Ref(publicFacingSG)
))

req = urllib2.Request("https://discovery.etcd.io/new")
with open ("../cloud-init", "r") as myfile:
    cloudInit = myfile.read()

ioClusterLaunchConfig = t.add_resource(autoscaling.LaunchConfiguration(
  "IOClusterLaunchConfig",
  ImageId=FindInMap("RegionMap", Ref("AWS::Region"), "AMI"),
  AssociatePublicIpAddress=True,
  InstanceType=FindInMap("Profile", Ref(profile_param), "InstanceType"),
  KeyName=Ref(keyPair_param),
  SecurityGroups= [ Ref(ioClusterSG)],
  DependsOn="ioGateway",
  BlockDeviceMappings= [
     ec2.BlockDeviceMapping(
       DeviceName="/dev/sda",
       Ebs=ec2.EBSBlockDevice(
        DeleteOnTermination="true",
        VolumeSize="50"
       )
     ),
     ec2.BlockDeviceMapping(
       DeviceName="/dev/sdb",
       VirtualName="ephemeral0"
     ),
     ec2.BlockDeviceMapping(
       DeviceName="/dev/sdc",
       VirtualName="ephemeral1"
     ),

  ],
  UserData=Base64(
    Join( "", [cloudInit.rpartition("##ETCD_TOKEN##")[0],
          Ref(discovery_param),
          cloudInit.rpartition("##ETCD_TOKEN##")[2]
          ]
    ))
))


elasticLB = t.add_resource(elb.LoadBalancer(
    'FrontHttpLB',
    ConnectionDrainingPolicy=elb.ConnectionDrainingPolicy(
        Enabled=True,
        Timeout=300,
    ),
    CrossZone=True,
    Listeners=[
        elb.Listener(
            LoadBalancerPort="80",
            InstancePort=7777,
            Protocol="HTTP",
        ),
        elb.Listener(
            LoadBalancerPort="443",
            InstancePort=7777,
            Protocol="HTTPS",
            SSLCertificateId=Join("",[
              "arn:aws:iam::",
              {
                 "Ref":"AWS::AccountId"
              },
              ":server-certificate/",
              Ref(sslCertificateId_param)
           ])
        ),
    ],
    HealthCheck=elb.HealthCheck(
        Target="TCP:7777",
        HealthyThreshold="3",
        UnhealthyThreshold="5",
        Interval="30",
        Timeout="5",
    ),
    SecurityGroups=[Ref(publicFacingSG)],
    Subnets=[Ref(privateSubnetA),Ref(privateSubnetB),Ref(privateSubnetC)]
))


autoScalingGroup = t.add_resource(autoscaling.AutoScalingGroup(
  "IOClusterAutoScale",
  MinSize="3",
  MaxSize="12",
  AvailabilityZones=[Select(0,GetAZs("")),Select(1,GetAZs("")),Select(2,GetAZs(""))],
  LaunchConfigurationName=Ref(ioClusterLaunchConfig),
  DesiredCapacity=FindInMap("Profile", Ref(profile_param), "ClusterSize"),
  LoadBalancerNames=[Ref(elasticLB)],
  VPCZoneIdentifier=[Ref(privateSubnetA),Ref(privateSubnetB),Ref(privateSubnetC)],
  Tags=[autoscaling.Tag("IoCluster",Ref("AWS::StackName"), True)]

))


RDS_SubnetGr = t.add_resource(rds.DBSubnetGroup(
    'DBSubnetGroup',
    DBSubnetGroupDescription=Join("-",[Ref("AWS::StackName"), " DB subnet group" ]),
    SubnetIds= [ Ref(privateSubnetA),Ref(privateSubnetB),Ref(privateSubnetC)]
))

DB = t.add_resource(rds.DBInstance(
    'DB',
    DBInstanceIdentifier=Join("-",[Ref("AWS::StackName"), "db" ]),
    DBName="postgres",
    DBSubnetGroupName=Ref(RDS_SubnetGr),
    MultiAZ=FindInMap("Profile", Ref(profile_param), "MultiAZ"),
    AllocatedStorage=FindInMap("Profile", Ref(profile_param), "DBAllocatedStorage"),
    BackupRetentionPeriod=FindInMap("Profile", Ref(profile_param), "DBBackupRetentionPeriod"),
    DBInstanceClass=FindInMap("Profile", Ref(profile_param), "DBInstanceType"),
    Engine="postgres",
    MasterUserPassword=Ref(dbPassword_param),
    MasterUsername="postgres",
    VPCSecurityGroups= [ Ref(ioClusterSG) ]
))


s3bucket = t.add_resource(Bucket(
  "S3Bucket",
  BucketName=Join(".",[Ref("AWS::StackName"),Ref(hostedzone)]),
  AccessControl=Private,
))


DNSRecord = t.add_resource(RecordSetType(
    "DNSRecord",
    HostedZoneName=Join("", [Ref(hostedzone), "."]),
    Comment="CNAME to cluster load balancer",
    Name=Join(".", ["*",Ref("AWS::StackName"),Ref(hostedzone)]),
    Type="CNAME",
    TTL="300",
    ResourceRecords=[GetAtt(elasticLB, "DNSName")]
))



t.add_output(Output(
    "S3BucketName",
    Value=Ref(s3bucket),
    Description="Name of S3 bucket to hold binaries"
))


t.add_output(Output(
    "AWSRegion",
    Description="AWS region where the cluster is hosted",
    Value=Ref("AWS::Region")
))


t.add_output(Output(
    "DBHost",
    Description="Host of the cluster's database",
    Value=GetAtt("DB", "Endpoint.Address")
))


t.add_output(Output(
    "DBPort",
    Description="Port of the cluster's database",
    Value=GetAtt("DB", "Endpoint.Port")
))

t.add_output(Output(
    "DiscoveryParam",
    Description="ETCD's discovery address",
    Value=Ref(discovery_param)
))

t.add_output(Output(
    "DomainName",
    Description="DNS Name of the load balancer",
    Value=Join(".", ["*",Ref("AWS::StackName"),Ref(hostedzone)])
))


print t.to_json()
