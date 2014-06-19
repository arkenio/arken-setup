#!/usr/bin/python


from troposphere import Base64, FindInMap, Parameter, Ref, Template, GetAZs, Join, Tags, Select
import troposphere.ec2 as ec2
import troposphere.autoscaling as autoscaling
import troposphere.elasticloadbalancing as elb
import re
import urllib2

t = Template()


"""
CoreOS AMIs
"""
t.add_mapping('RegionMap', {
    "ap-northeast-1" : {
        "AMI" : "ami-253b7324"
        },

    "sa-east-1" : {
        "AMI" : "ami-8fab0492"
        },

    "ap-southeast-2" : {
        "AMI" : "ami-9f0c68a5"
        },

    "ap-southeast-1" : {
        "AMI" : "ami-ac1b44fe"
        },

    "us-east-1" : {
        "AMI" : "ami-820ff0ea"
        },

    "us-west-2" : {
        "AMI" : "ami-7b8ff24b"
        },

    "us-west-1" : {
        "AMI" : "ami-ea5650af"
        },

    "eu-west-1" : {
        "AMI" : "ami-a73bf2d0"
        }
    })


"""
Declaration of parameters used in the cloud formation template
"""

instanceType_param = t.add_parameter(Parameter(
    "InstanceType",
    Description="EC2 instance type (m1.small, etc).",
    Type="String",
    Default="m3.2xlarge",
    AllowedValues=[ "t1.micro",
                    "m1.small",
                    "m1.medium",
                    "m1.large",
                    "m1.xlarge",
                    "m3.xlarge",
                    "m3.2xlarge",
                    "m2.xlarge",
                    "m2.2xlarge",
                    "m2.4xlarge",
                    "c1.medium",
                    "c1.xlarge",
                    "c3.xlarge",
                    "cc1.4xlarge",
                    "cc2.8xlarge",
                    "cg1.4xlarge",
                    "hi1.4xlarge",
                    "hs1.8xlarge"],
    ConstraintDescription="must be a valid EC2 instance type."
))

clusterSize_param = t.add_parameter(Parameter(
  "ClusterSize",
  Description= "Number of nodes in cluster (3-12)",
  MinValue= "3",
  MaxValue= "12",
  Default="3",
  Type="Number"
))

allowSSHFrom_param = t.add_parameter(Parameter(
  "AllowSSHFrom",
  Description="The net block (CIDR) taht SSH is available to.",
  MinLength="9",
  MaxLength="18",
  Default="0.0.0.0/0",
  Type="String",
  AllowedPattern="(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})"
                   "/(\\d{1,2})",
  ConstraintDescription="must be a valid IP CIDR range of the "
                        "form x.x.x.x/x."
))

keyPair_param = t.add_parameter(Parameter(
  "KeyPair",
  Description="The name of an EC2 Key Pair to allow SSH access to the instance.",
  Type="String"
))

"""
Network configuration

We create  :
 * a VPC
 * 2 subnets
 * an Internet Gateway
 * 2 security groups
 * 2 load balancers
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
            CidrIp=Ref(allowSSHFrom_param),
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
cloudInit = re.sub(ur'##ETCD_TOKEN##', urllib2.urlopen(req).read(), cloudInit)

ioClusterLaunchConfig = t.add_resource(autoscaling.LaunchConfiguration(
  "IOClusterLaunchConfig",
  ImageId=FindInMap("RegionMap", Ref("AWS::Region"), "AMI"),
  AssociatePublicIpAddress=True,
  InstanceType=Ref(instanceType_param),
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
     )
  ],
  UserData=Base64(cloudInit)
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
    ],
    HealthCheck=elb.HealthCheck(
        Target="TCP:7777",
        HealthyThreshold="3",
        UnhealthyThreshold="5",
        Interval="30",
        Timeout="5",
    ),
    SecurityGroups=[Ref(publicFacingSG)],
    Subnets=[Ref(publicSubnet)]
))


autoScalingGroup = t.add_resource(autoscaling.AutoScalingGroup(
  "IOClusterAutoScale",
  MinSize="3",
  MaxSize="12",
  AvailabilityZones=[Select(0,GetAZs("")),Select(1,GetAZs("")),Select(2,GetAZs(""))],
  LaunchConfigurationName=Ref(ioClusterLaunchConfig),
  DesiredCapacity=Ref(clusterSize_param),
  LoadBalancerNames=[Ref(elasticLB)],
  VPCZoneIdentifier=[Ref(privateSubnetA),Ref(privateSubnetB),Ref(privateSubnetC)],
  Tags=[autoscaling.Tag("IoCluster",Ref("AWS::StackName"), True)]

))




print t.to_json()
