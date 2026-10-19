# Bauumgebung für das Handy-Widget: JDK, Android-SDK und Gradle – ohne Android Studio.
# Bauen:  android/bauen.sh  (legt die APK unter widget/urlaubswidget.apk ab)
FROM eclipse-temurin:17-jdk
ENV ANDROID_HOME=/opt/android-sdk GRADLE_HOME=/opt/gradle
ENV PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$GRADLE_HOME/bin
RUN apt-get update && apt-get install -y --no-install-recommends unzip curl && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o /tmp/tools.zip https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip \
    && mkdir -p $ANDROID_HOME/cmdline-tools && unzip -q /tmp/tools.zip -d $ANDROID_HOME/cmdline-tools \
    && mv $ANDROID_HOME/cmdline-tools/cmdline-tools $ANDROID_HOME/cmdline-tools/latest && rm /tmp/tools.zip
RUN yes | sdkmanager --licenses > /dev/null \
    && sdkmanager --install "platforms;android-35" "build-tools;35.0.0" "platform-tools" > /dev/null \
    && chmod -R a+rX $ANDROID_HOME
RUN curl -fsSL -o /tmp/gradle.zip https://services.gradle.org/distributions/gradle-8.10.2-bin.zip \
    && unzip -q /tmp/gradle.zip -d /opt && mv /opt/gradle-8.10.2 $GRADLE_HOME && rm /tmp/gradle.zip
WORKDIR /src
