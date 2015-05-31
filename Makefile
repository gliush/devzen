.PHONY: vagrant

vagrant:
	vagrant up

run:
	vagrant ssh -c "docker run --rm -v /src:/site -p 4000:4000 andredumas/github-pages serve --watch --force_polling"

