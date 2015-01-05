#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  ford.py
#  
#  Copyright 2014 Christopher MacMackin <cmacmackin@gmail.com>
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#  
#  



import argparse
import markdown
from datetime import date

import ford.fortran_project
import ford.sourceform
import ford.output

def main():    
    # Setup the command-line options and parse them.
    parser = argparse.ArgumentParser(description="Document a program or library written in modern Fortran. Any command-line options over-ride those specified in the project file.")
    parser.add_argument("project_file",help="file containing the description and settings for the project",
                        type=argparse.FileType('r'))
    parser.add_argument("-d","--project_directory",help='top directory containing containing all source files for the project')
    parser.add_argument("-o","--output_dir",help="directory in which to place output files")
    parser.add_argument("-s","--css",help="custom style-sheet for the output")
    parser.add_argument("--exclude",action="append",help="any files which should not be included in the documentation")
    parser.add_argument("-e","--extensions",nargs="*",help="extensions which should be scanned for documentation (default: f90, f95, f03, f08)")

    args = parser.parse_args()

    #TODO: Integrate the Pelican Mathjax plugin--it will work better.
    md = markdown.Markdown(extensions=['markdown.extensions.meta',
        'markdown.extensions.codehilite','markdown.extensions.extra',
        'ford.mathjax'], output_format="html5")
    
    # Read in the project-file. This will contain global documentation (which
    # will appear on the homepage) as well as any information about the project
    # and settings for generating the documentation.
    proj_docs = args.project_file.read()
    proj_docs = md.convert(proj_docs)
    proj_data = md.Meta
    
    # Get the default options, and any over-rides, straightened out
    options = [u'project_directory',u'extensions',u'output_dir',u'css',u'exclude',
               u'project',u'author',u'author_description',u'author_pic',
               u'summary',u'github',u'bitbucket',u'facebook',u'twitter',
               u'google_plus',u'linkedin',u'email',u'website',u'project_github',
               u'project_bitbucket',u'project_website',u'project_download',
               u'project_sourceforge',u'project_url',u'display',u'version',
               u'year']
    defaults = {u'project_directory': u'./src',
                u'extensions':        [u"f90",u"f95",u"f03",u"f08"],
                u'output_dir':        u'./doc',
                u'project':           u'Fortran Program',
                u'project_url':       u'',
                u'display':           [u'public',u'protected'],
                u'year':              date.today().year
               }
    for option in options:
        if hasattr(args,option) and eval("args." + option):
            proj_data[option] = eval("args." + option)
        elif (option in proj_data):
            # Think if there is a safe  way to evaluate any expressions found in this list
            proj_data[option] = proj_data[option]
            if len(proj_data[option]) == 1: 
                proj_data[option] = proj_data[option][0]
        elif (not option in proj_data) and (option in defaults):
           proj_data[option] = defaults[option]

    if proj_data['project_directory'] in proj_data['output_dir']:
        print 'Error: output directory a subdirectory of directory containing source-code.'
        quit()

    if 'summary' in proj_data:
        if type(proj_data['summary']) == list:
            proj_data['summary'] = '\n'.join(proj_dat['summary'])
        proj_data['summary'] = md.convert(proj_data['summary'])
    if 'author_description' in proj_data:
        if type(proj_data['author_description']) == list:
            proj_data['author_description'] = '\n'.join(proj_data['author_description'])
        proj_data['author_description'] = md.convert(proj_data['author_description'])
    
    relative = (proj_data['project_url'] == '')
            
    # Parse the files in your project
    project = ford.fortran_project.Project(proj_data['project'],
                proj_data['project_directory'], proj_data['extensions'], 
                proj_data['display'])
    if len(project.files) < 1:
        print "Error: No source files with appropriate extension found in specified directory."
        quit()
    
    # Convert the documentation from Markdown to HTML. Make sure to properly
    # handle LateX and metadata.
    project.markdown(md)
    project.correlate()
    
    # Produce the documentation using Jinja2. Output it to the desired location
    # and copy any files that are needed (CSS, JS, images, fonts, source files,
    # etc.)
    print "Creating HTML documentation...\n"
    ford.output.print_html(project,proj_data,proj_docs,relative)
    
    return 0

if __name__ == '__main__':
    main()
