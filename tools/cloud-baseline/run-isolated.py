import os,socket,fcntl,struct
s=socket.socket(); req=struct.pack('16sH14s',b'lo',9,b''); fcntl.ioctl(s,0x8914,req);s.close()
base=os.path.abspath(os.path.dirname(__file__))
args=['bwrap','--unshare-pid','--unshare-ipc','--unshare-uts','--die-with-parent','--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--ro-bind',base+'/deps/root','/deps','--bind',base+'/src/baseline-runtime','/run-test','--bind',base+'/logs','/logs','--ro-bind',base+'/schema.sql','/schema.sql','--ro-bind',base+'/inside.sh','/inside.sh','--clearenv','--setenv','PATH','/usr/bin:/bin','--setenv','HOME','/tmp','--setenv','LD_LIBRARY_PATH','/deps/usr/lib/x86_64-linux-gnu','--chdir','/run-test','/bin/bash','/inside.sh']
os.execvp(args[0],args)
