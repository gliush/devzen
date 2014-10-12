up:
	vagrant plugin install vagrant-parallels
	vagrant init parallels/boot2docker
	vagrant up --provider parallels
	echo '# Now run the following commands:'
	echo 'export DOCKER_HOST_IP=$(vagrant ssh-config | sed -n "s/[ ]*HostName[ ]*//gp")'
	echo 'export DOCKER_HOST="tcp://${DOCKER_HOST_IP}:2375"'

build:
	docker run --rm -p 4000:4000 -v "/src:/src" grahamc/jekyll build

serve:
	docker run --rm -p 4000:4000 -v "/src:/src" grahamc/jekyll serve

inspect:
	docker run --rm -p 4000:4000 -it -v "/src:/src" --entrypoint /bin/bash grahamc/jekyll

