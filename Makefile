DOCKER=docker
RUN_CMD=run --rm -p 4000:4000 -v "/src:/src"
IMAGE=grahamc/jekyll

up:
	vagrant plugin install vagrant-parallels
	vagrant init parallels/boot2docker
	vagrant up --provider parallels
	echo '# Now run the following commands:'
	echo 'export DOCKER_HOST_IP=$(vagrant ssh-config | sed -n "s/[ ]*HostName[ ]*//gp")'
	echo 'export DOCKER_HOST="tcp://${DOCKER_HOST_IP}:2375"'

build:
	${DOCKER} ${RUN_CMD} ${IMAGE} build

serve:
	${DOCKER} ${RUN_CMD} ${IMAGE} serve

debug:
	${DOCKER} ${RUN_CMD} ${IMAGE} serve --watch

# run bash in the container to inspect everything
bash:
	${DOCKER} ${RUN_CMD} -it --entrypoint /bin/bash ${IMAGE}

