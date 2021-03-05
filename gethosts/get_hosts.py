import socket
import os
import sys

# reload(sys)
# sys.setdefaultencoding("utf-8")

def get_ip(host):
    """
    Get ip of host.
    """
    try:
        host_ip = socket.gethostbyname(host)
        return host_ip
    except:
        print("Unable to get IP of Hostname")

def main():
    f = open('./gethosts/hosts.txt', 'w')
    f.write("# GitHub Start\n")
    f.close()

    with open('./gethosts/domain.txt', "r") as ins:
        for host in ins:
            ip=get_ip(host.strip())
            with open('./gethosts/hosts.txt', 'a') as result:
                result.write(ip.strip('\n') + " " + host)
                print(ip.strip('\n') + " " + host)  # debug

    f = open('./gethosts/hosts.txt','a')
    f.write("\n# GitHub End\n")
    f.close()

if __name__ == "__main__":
    main()