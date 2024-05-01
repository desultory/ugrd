FROM gentoo/stage3

RUN echo 'nameserver 10.53.53.53' > /etc/resolv.conf
RUN getuto
RUN emerge-webrsync
RUN emerge -1 portage
RUN echo 'sys-kernel/installkernel -dracut' > /etc/portage/package.use/installkernel
RUN emerge dev-python/pip dev-vcs/git pax-utils --getbinpkg

RUN mkdir /dep_dir
WORKDIR /dep_dir
RUN git clone https://github.com/desultory/zenlib
RUN git clone https://github.com/desultory/pycpio
RUN pip install --break ./zenlib
RUN pip install --break ./pycpio

RUN mkdir /test_dir
WORKDIR /test_dir
COPY src src/
COPY MANIFEST.in .
COPY pyproject.toml .
RUN mkdir /etc/ugrd
RUN mkdir /etc/kernel/preinst.d -p
COPY hooks/51-ugrd.install /etc/kernel/preinst.d
COPY tests/vm.toml /etc/ugrd/config.toml
RUN pip install --break .

RUN ugrd
