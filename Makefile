.PHONY: run check deb appimage clean
run:
	python3 -m syscleaner
check:
	python3 -m compileall -q syscleaner
	python3 tools/check_i18n.py
	python3 -c "from syscleaner.tasks import load; g,t,w=load(); print(len(t),'tasks'); assert not w, w"
deb:
	./packaging/build_deb.sh
appimage:
	./packaging/build_appimage.sh
clean:
	rm -rf build dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
