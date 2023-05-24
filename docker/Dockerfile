FROM i386/debian:stretch

RUN echo "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20220630T220025Z/ stretch main" > /etc/apt/sources.list
RUN echo "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20220630T220025Z/ stretch-updates main" >> /etc/apt/sources.list
RUN echo "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20220630T220025Z/ stretch-backports main" >> /etc/apt/sources.list
RUN apt-get update && apt-get remove -y libnettle6 libelf1 && \
    apt-get install -y --allow-downgrades zlib1g=1:1.2.8.dfsg-5 && \
    apt-get autoremove -y
RUN apt-get install -y sudo build-essential python wget cmake gdb gawk mlocate \
            vim libc++-dev  g++-multilib g++ ninja-build sudo gdb gawk\
            git jq bc python python-colorama zsh libjsoncpp-dev zlib1g-dev \
            python-psycopg2 python-pexpect python-psutil locales \
            python-numpy python-argparse python-pip python-dev libpq-dev
ENV release 3.6.2
ENV llvm_version llvm-${release}

RUN wget --no-check-certificate http://llvm.org/releases/$release/$llvm_version.src.tar.xz && \
    mkdir $llvm_version && tar -xJf $llvm_version.src.tar.xz -C $llvm_version --strip-components=1 && \
    rm $llvm_version.src.tar.xz

WORKDIR /$llvm_version/tools
ENV clang_version cfe-$release
RUN wget --no-check-certificate http://llvm.org/releases/$release/$clang_version.src.tar.xz && \
    mkdir clang && tar -xJf $clang_version.src.tar.xz -C clang --strip-components=1 && \
    rm $clang_version.src.tar.xz

WORKDIR /$llvm_version/tools/clang/tools
RUN wget --no-check-certificate http://llvm.org/releases/$release/clang-tools-extra-$release.src.tar.xz && \
    mkdir extra && tar -xJf clang-tools-extra-$release.src.tar.xz -C extra --strip-components=1 && \
    rm clang-tools-extra-$release.src.tar.xz

RUN mkdir /$llvm_version/build /$llvm_version/Release
WORKDIR /$llvm_version/build
RUN cmake ../ -DCMAKE_INSTALL_PREFIX=/$llvm_version/Release -DLLVM_TARGETS_TO_BUILD=X86 \
              -DBUILD_SHARED_LIBS=true -DLLVM_ENABLE_ASSERTIONS=false -DLLVM_ENABLE_RTTI=true \
              -DLLVM_BUILD_32_BITS=true \
              -DLLVM_ENABLE_PIC=true -DCMAKE_BUILD_TYPE=Release -DLLVM_TARGET_ARCH=i486-linux-gnu \
              -G "Ninja"
RUN ninja install

WORKDIR /
RUN wget http://codesynthesis.com/download/odb/2.4/odb_2.4.0-1_i386.deb && \
    dpkg -i odb_2.4.0-1_i386.deb && rm odb_2.4.0-1_i386.deb
RUN wget http://codesynthesis.com/download/odb/2.4/libodb-2.4.0.tar.gz && \
    tar xf libodb-2.4.0.tar.gz && rm libodb-2.4.0.tar.gz
WORKDIR /libodb-2.4.0
RUN ./configure --enable-shared && make -j $(nproc) && make install
WORKDIR /
RUN wget http://codesynthesis.com/download/odb/2.4/libodb-pgsql-2.4.0.tar.gz && \
    tar xf libodb-pgsql-2.4.0.tar.gz && rm libodb-pgsql-2.4.0.tar.gz
WORKDIR /libodb-pgsql-2.4.0
RUN ./configure --enable-shared && make -j $(nproc) && make install

RUN echo "/usr/local/lib" > /etc/ld.so.conf.d/usr-local-lib.conf
RUN ldconfig

RUN pip install --upgrade -v pip subprocess32 lockfile sqlalchemy==1.3.24 -i https://pypi.python.org/simple/
RUN pip install pyyaml
RUN ln -s /usr/lib/libjsoncpp.so.0 /usr/lib/libjsoncpp.so.1
RUN updatedb

RUN echo "LLVM_DIR=/$llvm_version/Release/share/llvm/cmake" >>/etc/environment
RUN echo "LD_LIBRARY_PATH=/$llvm_version/Release/lib" >>/etc/environment
RUN echo "LIBRARY_PATH=/usr/local/lib" >>/etc/environment
RUN echo "PATH=$PATH:/$llvm_version/Release/bin" >>/etc/environment

# Set locale to C.UTF-8 instead of us_EN.UTF-8
RUN locale-gen C.UTF-8
RUN locale -a
RUN update-locale LANG=C.UTF-8
