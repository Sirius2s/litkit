import socket


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
    f.close()

    with open('./gethosts/domain.txt', "r") as lins:
        for host in lins:
            if '#' in host or host == '' or host == '\n':
                with open('./gethosts/hosts.txt', 'a') as result:
                    result.write(host)
                    continue

            ip = get_ip(host.strip())
            with open('./gethosts/hosts.txt', 'a') as result:
                result.write(ip.strip('\n') + "\t" + host)


if __name__ == "__main__":
    main()
